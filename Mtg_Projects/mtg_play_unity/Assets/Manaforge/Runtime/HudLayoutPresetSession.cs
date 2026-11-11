using System;
using System.Threading;
using System.Threading.Tasks;

namespace Manaforge.Play
{
    // Storage operations shared by live presentation controls; never applies geometry.
    public sealed class HudLayoutPresetSession : IDisposable
    {
        private readonly ILayoutPresetStore store;
        private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private bool disposed;
        public LayoutPresetLibrary Library { get; private set; }=LayoutPresetLibrary.Empty;
        public PresetStoreResult Receipt { get; private set; }
        public bool Busy { get; private set; }
        public bool CanWrite=>!disposed && !Busy && Receipt?.CanWrite==true;
        public HudLayoutPresetSession(ILayoutPresetStore store){this.store=store??throw new ArgumentNullException(nameof(store));}
        public async Task<bool> RefreshAsync()
        {
            if(disposed || Busy)return false;Busy=true;
            try{var result=await store.ReadAsync(cancellation.Token);if(disposed)return false;Receipt=result;Library=result.Library??LayoutPresetLibrary.Empty;return result.Success;}
            catch(OperationCanceledException){return false;}
            catch(Exception){if(!disposed)Receipt=new PresetStoreResult(PresetStoreStatus.IoError);return false;}
            finally{Busy=false;if(disposed)cancellation.Dispose();}
        }
        public async Task<bool> WriteAsync(LayoutPresetLibrary library)
        {
            if(!CanWrite)return false;Busy=true;
            try{
                var result=await store.WriteAsync(library,Receipt.Revision,cancellation.Token);if(disposed)return false;
                if(result.Success){Receipt=result;Library=result.Library;return true;}
                // Conflict and IO errors require a fresh read before another write.
                Receipt=result;return false;
            }catch(OperationCanceledException){return false;}
            catch(Exception){if(!disposed)Receipt=new PresetStoreResult(PresetStoreStatus.IoError);return false;}
            finally{Busy=false;if(disposed)cancellation.Dispose();}
        }
        public static string Describe(PresetStoreStatus code)
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
        public void Dispose(){if(disposed)return;disposed=true;cancellation.Cancel();if(!Busy)cancellation.Dispose();}
    }
}
