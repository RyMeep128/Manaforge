using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Explicit-save fixture controls. File operations never run in the layout/input callbacks.
    public sealed class LayoutPresetPanel : VisualElement,IDisposable
    {
        private readonly ILayoutPresetStore store;
        private readonly LayoutPresetApplicator binding;
        private readonly Action<bool> lockEditing;
        private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private readonly List<Action> cleanup=new List<Action>();
        private readonly VisualElement controls=new VisualElement(),confirmation=new VisualElement();
        private readonly PopupField<string> selector=new PopupField<string>("Preset",new List<string>{"Default"},0);
        private readonly TextField nameField=new TextField("Name"){name="preset-name"};
        private readonly Label status=new Label{enableRichText=false},confirmationText=new Label{enableRichText=false};
        private readonly Button save,saveAs,rename,delete;
        private LayoutPresetLibrary library=LayoutPresetLibrary.Empty;
        private PresetStoreResult receipt;
        private HudLayoutPreset working;
        private JToken baseline;
        private string selectedId,message="Loading presets";
        private Func<Task> pendingConfirmation;
        private bool disposed;
        public bool Busy { get; private set; }
        public bool Dirty=>baseline==null || !JToken.DeepEquals(baseline,binding.Fingerprint(working));
        public bool HasPendingConfirmation=>pendingConfirmation!=null;
        public string SelectedId=>selectedId;
        public PresetStoreStatus LastStatus { get; private set; }
        public Task Initialization { get; }
        public LayoutPresetPanel(ILayoutPresetStore store,LayoutPresetApplicator binding,Action<bool> lockEditing)
        {
            this.store=store;this.binding=binding;this.lockEditing=lockEditing;name="layout-presets";AddToClassList("mf-layout-presets");
            controls.AddToClassList("mf-layout-toolbar");Add(controls);selector.name="preset-selector";controls.Add(selector);controls.Add(nameField);nameField.tooltip="1–64 characters; unique name; Default is reserved";
            Button AddButton(string text,Func<Task> action){
                var button=new Button(()=>Invoke(action)){text=text};controls.Add(button);cleanup.Add(()=>button.clickable=null);return button;
            }
            save=AddButton("Save",async()=>{await SaveAsync(null,false);});saveAs=AddButton("Save As",async()=>{await SaveAsync(nameField.value,true);});
            AddButton("Load",async()=>{await LoadAsync(selectedId);});rename=AddButton("Rename",async()=>{await RenameAsync(nameField.value);});
            delete=AddButton("Delete",async()=>{await DeleteAsync();});AddButton("Restore Default",()=>{RestoreDefault();return Task.CompletedTask;});
            AddButton("Refresh list",async()=>{await ReadAsync(false);});
            EventCallback<ChangeEvent<string>> selection=ev=>{selectedId=library.Presets.FirstOrDefault(p=>p.Name==ev.newValue)?.Id;Refresh();};
            selector.RegisterValueChangedCallback(selection);cleanup.Add(()=>selector.UnregisterValueChangedCallback(selection));
            Add(status);confirmation.AddToClassList("mf-layout-confirm");confirmation.Add(confirmationText);
            var confirm=new Button(()=>{var action=pendingConfirmation;pendingConfirmation=null;Refresh();if(action!=null)Invoke(action);}){text="Confirm",name="preset-confirm"};
            var cancel=new Button(()=>{pendingConfirmation=null;Refresh();}){text="Cancel",name="preset-cancel"};
            confirmation.Add(confirm);confirmation.Add(cancel);cleanup.Add(()=>confirm.clickable=null);cleanup.Add(()=>cancel.clickable=null);Add(confirmation);
            baseline=binding.Fingerprint();Initialization=ReadAsync(true);
        }
        private async void Invoke(Func<Task> operation)
        {
            try{await operation();}catch(OperationCanceledException){}catch(Exception){if(!disposed)Error(PresetStoreStatus.IoError);}
        }
        private bool CanStart=>!disposed && !Busy && pendingConfirmation==null;
        private static string Describe(PresetStoreStatus code)
        {
            switch(code){
                case PresetStoreStatus.Ready:return "Presets ready";
                case PresetStoreStatus.Missing:return "No saved presets yet";
                case PresetStoreStatus.RecoveredBackup:return "Saved presets recovered from backup";
                case PresetStoreStatus.Corrupt:return "Saved presets are damaged. Default is available; Save As preserves the damaged file";
                case PresetStoreStatus.UnsupportedVersion:return "Presets use an unsupported app version; storage is read-only";
                case PresetStoreStatus.Conflict:return "Changed in another window; Refresh list before saving";
                case PresetStoreStatus.ValidationError:return "Invalid preset name or layout";
                case PresetStoreStatus.Busy:return "Preset storage is in use; retry with Refresh list";
                default:return "Could not access saved presets; retry with Refresh list";
            }
        }
        private void Error(PresetStoreStatus code){LastStatus=code;message=Describe(code);Refresh();}
        private void RefreshChoices()
        {
            selector.choices=new[]{"Default"}.Concat(library.Presets.Select(p=>p.Name)).ToList();
            var preset=library.Find(selectedId);if(preset==null)selectedId=null;
            selector.SetValueWithoutNotify(preset?.Name??"Default");Refresh();
        }
        public void RefreshDirty(){if(!disposed && !binding.IsApplying)Refresh();}
        private void Refresh()
        {
            if(disposed)return;
            bool blocked=Busy || pendingConfirmation!=null;controls.SetEnabled(!blocked);lockEditing?.Invoke(blocked);
            bool writable=receipt?.CanWrite==true;
            save.SetEnabled(writable && selectedId!=null);saveAs.SetEnabled(writable);rename.SetEnabled(writable && selectedId!=null);delete.SetEnabled(writable && selectedId!=null);
            confirmation.style.display=pendingConfirmation==null?DisplayStyle.None:DisplayStyle.Flex;
            status.text=message+(Dirty?" | Unsaved changes":"")+(Busy?" | Busy":"")+(receipt!=null && !receipt.CanWrite?" | Storage read-only":"");
        }
        private void Confirm(string text,Func<Task> action){confirmationText.text=text;pendingConfirmation=action;Refresh();}
        private void SetLoaded(HudLayoutPreset preset,LayoutPresetApplication application)
        {
            working=preset;baseline=binding.Fingerprint(working);message=application.Adjustments.Count==0?"Layout loaded":"Layout loaded with adjustments: "+string.Join("; ",application.Adjustments);
        }
        public void SelectPreset(string id)
        {if(!CanStart)return;if(id!=null && library.Find(id)==null)throw new ArgumentException("PRESET_NOT_FOUND");selectedId=id;RefreshChoices();}
        private async Task ReadAsync(bool restore)
        {
            if(!CanStart)return;Busy=true;Refresh();
            try{
                var result=await store.ReadAsync(cancellation.Token);if(disposed)return;
                LastStatus=result.Status;receipt=result;message=Describe(result.Status);
                if(result.Library==null)return;library=result.Library;
                if(restore){
                    var preset=result.Success?library.Find(library.LastSelectedId):null;selectedId=preset?.Id;
                    var application=binding.Prepare(preset??binding.BuiltInDefault());
                    if(application!=null && binding.Apply(application)){
                        SetLoaded(preset,application);
                        if(result.Success && library.LastSelectedId!=null && preset==null)message="Previous preset unavailable; Default loaded";
                        if(result.Status!=PresetStoreStatus.Ready && result.Status!=PresetStoreStatus.Missing)message=Describe(result.Status)+"; "+message;
                    }else message="Preset could not be applied; using default workspace";
                }
                RefreshChoices();
            }catch(OperationCanceledException){}catch(Exception){if(!disposed)Error(PresetStoreStatus.IoError);}
            finally{Busy=false;if(!disposed)Refresh();}
        }
        private async Task<bool> Persist(LayoutPresetLibrary next)
        {
            var result=await store.WriteAsync(next,receipt?.Revision,cancellation.Token);if(disposed)return false;
            LastStatus=result.Status;
            if(!result.Success){if(result.Status==PresetStoreStatus.UnsupportedVersion)receipt=result;message=Describe(result.Status);Refresh();return false;}
            library=result.Library;receipt=result;return true;
        }
        public async Task<bool> SaveAsync(string name,bool asNew)
        {
            if(!CanStart || receipt?.CanWrite!=true)return false;
            Busy=true;Refresh();
            try{
                var target=asNew?null:library.Find(selectedId);if(!asNew && target==null)return false;
                var saved=binding.Capture(asNew?Guid.NewGuid().ToString("N"):target.Id,asNew?name:target.Name,asNew?working:target);
                if(!await Persist(library.Save(saved)))return false;
                selectedId=saved.Id;working=saved;baseline=binding.Fingerprint(working);message="Preset saved";RefreshChoices();return true;
            }catch(OperationCanceledException){return false;}catch(ArgumentException){Error(PresetStoreStatus.ValidationError);return false;}
            catch(Exception){if(!disposed)Error(PresetStoreStatus.IoError);return false;}finally{Busy=false;if(!disposed)Refresh();}
        }
        public async Task<bool> LoadAsync(string id,bool discard=false)
        {
            if(!CanStart)return false;
            if(Dirty && !discard){Confirm("Discard unsaved layout changes and load this preset?",async()=>{await LoadAsync(id,true);});return false;}
            var target=id==null?null:library.Find(id);if(id!=null && target==null){Error(PresetStoreStatus.ValidationError);return false;}
            var application=binding.Prepare(target??binding.BuiltInDefault());if(application==null){Error(PresetStoreStatus.ValidationError);return false;}
            Busy=true;Refresh();
            try{
                if(receipt?.CanWrite==true && !await Persist(library.Select(id)))return false;
                if(!binding.Apply(application)){Error(PresetStoreStatus.ValidationError);return false;}
                selectedId=id;SetLoaded(target,application);RefreshChoices();return true;
            }catch(OperationCanceledException){return false;}catch(Exception){if(!disposed)Error(PresetStoreStatus.IoError);return false;}
            finally{Busy=false;if(!disposed)Refresh();}
        }
        public bool RestoreDefault(bool discard=false)
        {
            if(!CanStart)return false;
            if(Dirty && !discard){Confirm("Discard unsaved layout changes and restore Default?",()=>{RestoreDefault(true);return Task.CompletedTask;});return false;}
            var application=binding.Prepare(binding.BuiltInDefault());if(application==null || !binding.Apply(application)){Error(PresetStoreStatus.ValidationError);return false;}
            selectedId=null;SetLoaded(null,application);message="Default restored in memory";RefreshChoices();return true;
        }
        public async Task<bool> RenameAsync(string name)
        {
            if(!CanStart || receipt?.CanWrite!=true || selectedId==null)return false;Busy=true;Refresh();
            try{if(!await Persist(library.Rename(selectedId,name)))return false;message="Preset renamed";RefreshChoices();return true;}
            catch(OperationCanceledException){return false;}catch(ArgumentException){Error(PresetStoreStatus.ValidationError);return false;}
            catch(Exception){if(!disposed)Error(PresetStoreStatus.IoError);return false;}finally{Busy=false;if(!disposed)Refresh();}
        }
        public async Task<bool> DeleteAsync(bool confirmed=false)
        {
            if(!CanStart || receipt?.CanWrite!=true || selectedId==null)return false;
            if(!confirmed){Confirm("Delete this saved preset? Current workspace changes will be kept.",async()=>{await DeleteAsync(true);});return false;}
            string id=selectedId;Busy=true;Refresh();
            try{if(!await Persist(library.Delete(id)))return false;
                if(working?.Id==id)baseline=null;selectedId=null;message="Preset deleted";RefreshChoices();return true;}
            catch(OperationCanceledException){return false;}catch(Exception){if(!disposed)Error(PresetStoreStatus.IoError);return false;}
            finally{Busy=false;if(!disposed)Refresh();}
        }
        public void Dispose()
        {
            if(disposed)return;disposed=true;pendingConfirmation=null;cancellation.Cancel();
            foreach(var action in cleanup)action();cleanup.Clear();lockEditing?.Invoke(false);RemoveFromHierarchy();
            // Worker tasks retain their token; dispose the source after initialization has unwound.
            Initialization.ContinueWith(_=>cancellation.Dispose(),TaskScheduler.Default);
        }
    }
}
