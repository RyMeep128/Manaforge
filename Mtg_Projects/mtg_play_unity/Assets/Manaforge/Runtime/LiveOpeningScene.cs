using System;
using System.Collections;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Explicit public-deck live opening spike. Existing card and decision components only.
    public sealed class LiveOpeningScene : MonoBehaviour
    {
        private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private ViewerBootstrapPipe pipe;private Task<ViewerBootstrap> reading;private Task consuming;
        private ViewerCardSurface surface;private ViewerSessionHost host;private ViewerDecisionPanel panel;
        private PanelSettings settings;private UIDocument document;private string output;private Label status;
        private int snapshots,acks;private bool capture,choiceReported;
        private bool Report(string name,bool cleared=false)
        {
            try{var value=new JObject{["probe_version"]=1,["live_opening"]=true,["snapshot_count"]=Volatile.Read(ref snapshots),["ack_count"]=Volatile.Read(ref acks),["viewer_cleared"]=cleared};
                string path=Path.Combine(output,name+".json");File.WriteAllText(path+".tmp",value.ToString());File.Move(path+".tmp",path);return true;}catch{return false;}
        }
        private void Fail(){host?.Dispose();Report("failed");Application.Quit(1);}
        private IEnumerator Start()
        {
            output=ArtworkFixtureScene.Argument("-manaforgeLiveOpening");capture=ArtworkFixtureScene.Argument("-manaforgeLiveCapture")=="1";
            try{Directory.CreateDirectory(output);pipe=ViewerBootstrapPipe.FromStandardInput();reading=pipe.ReadBootstrapAsync(5000,cancellation.Token);}catch{Fail();yield break;}
            while(!reading.IsCompleted)yield return null;
            if(reading.Status!=TaskStatus.RanToCompletion || reading.Result.SessionId!="live-opening" || reading.Result.ViewerId!="human" || reading.Result.ArtworkDirectory!=null){Fail();yield break;}
            try{
                settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");settings.scaleMode=PanelScaleMode.ScaleWithScreenSize;settings.referenceResolution=new Vector2Int(1280,720);
                document=gameObject.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.flexGrow=1;root.style.paddingLeft=20;root.style.paddingTop=15;root.style.backgroundColor=new Color(.025f,.055f,.075f);
                var title=new Label("LIVE XMAGE — HUMAN vs AI OPENING");title.style.fontSize=23;title.style.color=Color.white;root.Add(title);
                status=new Label("Connecting to the owned Java gateway…");status.style.color=Color.white;root.Add(status);
                var note=new Label("Public Forest/Memnite decks. Opening decision only; artwork cache and later gameplay are not connected.");note.style.color=Color.gray;root.Add(note);
                var stage=new VisualElement();stage.style.flexDirection=FlexDirection.Row;stage.style.flexGrow=1;stage.style.marginTop=10;root.Add(stage);
                surface=new ViewerCardSurface(stage);surface.CardsRoot.style.width=720;surface.CardsRoot.style.flexShrink=0;surface.InspectionView.SetPresentation(CardPresentationMode.Full,210);
                host=new ViewerSessionHost(surface,reading.Result,pipe.WaitForOwnerCloseAsync(cancellation.Token),false);
                var choices=new VisualElement();choices.style.width=290;choices.style.flexShrink=0;stage.Add(choices);panel=new ViewerDecisionPanel(choices,host);
                var token=cancellation.Token;consuming=Task.Run(()=>{while(!token.IsCancellationRequested && !host.Completion.IsCompleted){if(host.TryTake(out var update))using(update){if(update.Receive.Type=="snapshot")Interlocked.Increment(ref snapshots);if(update.Receive.Type=="ack")Interlocked.Increment(ref acks);}else Thread.Sleep(10);}});
            }catch{Fail();yield break;}
            double deadline=Time.realtimeSinceStartupAsDouble+20;
            while(!host.Completion.IsCompleted && (surface.CardsRoot.childCount!=7 || panel.Root.Q<Button>("decision-option-0")==null)){
                host.Tick();panel.Tick();if(Time.realtimeSinceStartupAsDouble>=deadline){Fail();yield break;}yield return null;
            }
            if(host.Completion.IsCompleted || !host.Authenticated){Fail();yield break;}
            foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
            var inspect=new VisualElement();inspect.style.flexDirection=FlexDirection.Row;document.rootVisualElement.Insert(3,inspect);int count=0;
            foreach(string objectId in surface.PresentedObjectIds()){string id=objectId;inspect.Add(new Button(()=>host.Inspect(id)){text="Inspect "+(++count)});}
            status.text="Connected to real XMage. Inspect your opening hand, then choose Yes or No.";
            if(capture)yield return Capture("connected.png");if(!Report("ready")){Application.Quit(1);yield break;}
            if(ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1"){
                // Opt-in public-deck acceptance script through the actual mounted UI callback.
                var button=panel.Root.Q<Button>("decision-option-0");using(var input=NavigationSubmitEvent.GetPooled()){input.target=button;button.SendEvent(input);}
            }
            while(!host.Completion.IsCompleted){
                host.Tick();panel.Tick();
                if(!choiceReported && Volatile.Read(ref acks)>=2){
                    host.Cancel();host.Tick();panel.Tick();inspect.Clear();
                    status.text="Choice submitted to XMage. Next-state support ends here; viewer cleared. No confirmed result is claimed.";
                    if(capture)yield return Capture("choice.png");if(!Report("choice",true)){Application.Quit(1);yield break;}choiceReported=true;
                }
                yield return null;
            }
            host.Tick();panel.Dispose();host.Dispose();surface.Dispose();while(!consuming.IsCompleted)yield return null;
            bool cleared=document.rootVisualElement.Query<CardView>().ToList().Count==0;
            Report("closed",cleared);Application.Quit(cleared && host.Completion.Result.CleanupConfirmed?0:1);
        }
        private IEnumerator Capture(string name)
        {
            var target=new RenderTexture(1280,720,24);Texture2D pixels=null;var previous=RenderTexture.active;
            try{target.Create();settings.targetTexture=target;for(int i=0;i<20;i++)yield return null;yield return new WaitForEndOfFrame();pixels=new Texture2D(1280,720,TextureFormat.RGBA32,false);RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1280,720),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(output,name),pixels.EncodeToPNG());}
            finally{settings.targetTexture=null;RenderTexture.active=previous;if(pixels!=null)Destroy(pixels);target.Release();Destroy(target);}
        }
        private void OnDestroy(){cancellation.Cancel();panel?.Dispose();host?.Dispose();surface?.Dispose();pipe?.Dispose();reading?.ContinueWith(done=>{if(done.Status==TaskStatus.RanToCompletion)done.Result?.Dispose();else _=done.Exception;},TaskScheduler.Default);consuming?.ContinueWith(done=>{_=done.Exception;},TaskScheduler.Default);if(settings!=null)Destroy(settings);cancellation.Dispose();}
    }
}
