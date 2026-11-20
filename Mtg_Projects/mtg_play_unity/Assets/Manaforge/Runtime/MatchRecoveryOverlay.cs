using System;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Owned local lifecycle IPC. Gameplay still uses the authenticated viewer channel.
    public sealed class MatchRecoveryOverlay : IDisposable
    {
        private readonly string directory;
        private readonly bool hosting;
        private readonly VisualElement shade,card,banner;
        private readonly Label title,detail,bannerText;
        private readonly Button addAi,resume,end,view,reopen,confirm,cancel;
        private bool paused,visible,ended,disposed,confirming,submitted;
        private DateTime lastWrite;
        public bool Paused=>paused;
        public bool Ended=>ended;
        public MatchRecoveryOverlay(VisualElement root,string directory)
        {
            this.directory=directory;
            string role=Path.Combine(directory,"recovery-role.json");
            hosting=File.Exists(role) && (bool?)JObject.Parse(File.ReadAllText(role))["host"]==true;
            banner=new VisualElement{name="match-paused-banner"};banner.style.position=Position.Absolute;banner.style.top=8;banner.style.left=8;banner.style.right=8;banner.style.flexDirection=FlexDirection.Row;banner.style.backgroundColor=new UnityEngine.Color(.08f,.12f,.16f,.98f);banner.style.paddingLeft=12;banner.style.paddingRight=12;banner.style.paddingTop=8;banner.style.paddingBottom=8;
            bannerText=new Label("Game paused");bannerText.style.flexGrow=1;banner.Add(bannerText);
            reopen=Button("recovery-reopen","Recovery menu",()=>Show(true));banner.Add(reopen);root.Add(banner);
            shade=new VisualElement{name="match-recovery-overlay"};shade.AddToClassList("mf-game-menu-overlay");GameplayTheme.Attach(shade);root.Add(shade);
            card=new VisualElement{name="match-recovery-card"};card.AddToClassList("mf-game-menu-card");shade.Add(card);
            title=new Label("Player disconnected"){name="game-menu-title"};card.Add(title);
            detail=new Label{enableRichText=false};detail.style.whiteSpace=WhiteSpace.Normal;card.Add(detail);
            addAi=Button("recovery-add-ai","Add AI",()=>Send("add_ai"));card.Add(addAi);
            resume=Button("recovery-resume","Resume Game",()=>Send("resume"));card.Add(resume);
            end=Button("recovery-end-game","End Game",()=>{confirming=true;RefreshConfirmation();});card.Add(end);
            view=Button("recovery-view-battlefield","View Battlefield",()=>Show(false));card.Add(view);
            confirm=Button("recovery-confirm-end","End game without a winner",()=>Send("end_game"));card.Add(confirm);
            cancel=Button("recovery-cancel-end","Cancel",()=>{confirming=false;RefreshConfirmation();});card.Add(cancel);
            RefreshConfirmation();Show(false);banner.style.display=DisplayStyle.None;
            root.RegisterCallback<KeyDownEvent>(Key,TrickleDown.TrickleDown);
        }
        private static Button Button(string name,string text,Action action){var value=new Button(action){name=name,text=text};GameplayTheme.Button(value);return value;}
        private void RefreshConfirmation(){confirm.style.display=cancel.style.display=confirming?DisplayStyle.Flex:DisplayStyle.None;foreach(var button in new[]{addAi,resume,end,view})button.style.display=confirming?DisplayStyle.None:DisplayStyle.Flex;title.text=confirming?"End this game for everyone?":"Game paused";}
        private void Show(bool value){visible=value;shade.style.display=value?DisplayStyle.Flex:DisplayStyle.None;if(value){shade.BringToFront();view.Focus();}}
        private void Key(KeyDownEvent input){if(!hosting || !paused || input.keyCode!=UnityEngine.KeyCode.Escape)return;confirming=false;RefreshConfirmation();Show(!visible);input.StopImmediatePropagation();}
        private void Send(string action){
            if(submitted)return;
            try{string path=Path.Combine(directory,"recovery-action.json");if(File.Exists(path))return;string temporary=path+".tmp";File.WriteAllText(temporary,new JObject{["action"]=action}.ToString());File.Move(temporary,path);submitted=true;detail.text="Waiting for the host session…";}catch(IOException){detail.text="Recovery is busy. Try again.";}
        }
        public void Tick()
        {
            if(disposed)return;
            string path=Path.Combine(directory,"recovery-state.json");
            try{
                if(!File.Exists(path))return;var stamp=File.GetLastWriteTimeUtc(path);if(stamp==lastWrite)return;
                JObject state;using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))using(var reader=new StreamReader(stream))state=JObject.Parse(reader.ReadToEnd());lastWrite=stamp;
                bool previous=paused;paused=(bool?)state["paused"]==true;ended=(bool?)state["ended"]==true;submitted=false;
                banner.style.display=paused && !ended?DisplayStyle.Flex:DisplayStyle.None;
                bannerText.text=hosting?"Game paused · waiting for the host to resume":"Game paused · waiting for the host";
                reopen.style.display=hosting?DisplayStyle.Flex:DisplayStyle.None;
                addAi.SetEnabled(hosting && (string)state["controller"]!="ai" && (bool?)state["connected"]!=true);
                resume.SetEnabled(hosting && (bool?)state["can_resume"]==true);end.SetEnabled(hosting);
                detail.text=(string)state["error"]??((bool?)state["can_resume"]==true?"The seat is ready. Resume when you are ready.":"Waiting for the disconnected player. Add the hardest AI or let someone rejoin with the invite.");
                if(!paused || ended){Show(false);confirming=false;RefreshConfirmation();}else if(!previous && hosting)Show(true);
            }catch(IOException){}catch(Newtonsoft.Json.JsonException){}
        }
        public void Dispose(){if(disposed)return;disposed=true;shade.parent?.UnregisterCallback<KeyDownEvent>(Key,TrickleDown.TrickleDown);shade.RemoveFromHierarchy();banner.RemoveFromHierarchy();}
    }
}
