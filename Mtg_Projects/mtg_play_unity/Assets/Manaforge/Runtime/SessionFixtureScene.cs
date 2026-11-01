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
    // Explicit public fixture scene. Not a product launcher or real-engine match.
    public sealed class SessionFixtureScene : MonoBehaviour
    {
        private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private ViewerBootstrapPipe pipe;private ViewerCardSurface surface;private ViewerSessionHost host;
        private PanelSettings settings;private UIDocument document;private Label status;private string output;
        private Task<ViewerBootstrap> reading,validated;private Task consuming;private int snapshots,events,unexpected;
        private bool capture,decisions,scripted,decisionReported;private int acknowledgements,results;private ViewerDecisionPanel decisionPanel;
        private bool Report(string name,string code,bool cleared=false)
        {
            try {
                var report=new JObject{["probe_version"]=1,["fixture_only"]=true,["code"]=code,["snapshot_count"]=Volatile.Read(ref snapshots),["event_count"]=Volatile.Read(ref events),["viewer_cleared"]=cleared};
                if(decisions){report["ack_count"]=Volatile.Read(ref acknowledgements);report["result_count"]=Volatile.Read(ref results);report["decision_panel_cleared"]=decisionPanel!=null && decisionPanel.Root.Q<Button>()==null;}
                string path=Path.Combine(output,name+".json");File.WriteAllText(path+".tmp",report.ToString());File.Move(path+".tmp",path);return true;
            }catch{return false;}
        }
        private void Fail(string code){host?.Dispose();Report("failed",code);Application.Quit(1);}
        private IEnumerator Start()
        {
            decisions=ArtworkFixtureScene.Argument("-manaforgeSessionDecisions")=="1";scripted=ArtworkFixtureScene.Argument("-manaforgeSessionDecisionScript")=="1";
            output=ArtworkFixtureScene.Argument("-manaforgeSessionFixture");capture=ArtworkFixtureScene.Argument("-manaforgeSessionCapture")=="1";
            try{Directory.CreateDirectory(output);pipe=ViewerBootstrapPipe.FromStandardInput();reading=pipe.ReadBootstrapAsync(5000,cancellation.Token);}
            catch{Fail("SESSION_FIXTURE_BOOTSTRAP_FAILED");yield break;}
            while(!reading.IsCompleted)yield return null;
            if(reading.Status!=TaskStatus.RanToCompletion){Fail("SESSION_FIXTURE_BOOTSTRAP_FAILED");yield break;}
            validated=Task.Run(()=>SessionFixtureBootstrap.ValidateAndReissue(reading.Result));
            while(!validated.IsCompleted)yield return null;
            if(validated.Status!=TaskStatus.RanToCompletion || validated.Result==null){Fail("SESSION_FIXTURE_CONTEXT");yield break;}
            try {
                settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");settings.scaleMode=PanelScaleMode.ScaleWithScreenSize;settings.referenceResolution=new Vector2Int(1280,720);
                document=gameObject.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.flexGrow=1;root.style.backgroundColor=new Color(.025f,.055f,.075f);root.style.paddingLeft=24;root.style.paddingTop=20;
                var title=new Label("AUTHENTICATED SESSION FIXTURE — NOT A LIVE GAME");title.style.fontSize=22;title.style.color=Color.white;root.Add(title);
                status=new Label("Connecting to the fixture gateway…");status.style.color=Color.white;status.style.marginBottom=12;root.Add(status);
                var note=new Label(decisions?"Public synthetic choices only. No XMage, real game or automatic play.":"Public synthetic data. Artwork, rules and gameplay controls are unavailable in this integration fixture.");note.style.color=new Color(.75f,.8f,.85f);root.Add(note);
                var inspect=new Button(()=>host?.Inspect("fixture-0002")){text="Inspect public fixture card"};inspect.style.width=230;inspect.style.marginTop=10;inspect.style.marginBottom=10;root.Add(inspect);
                var stage=new VisualElement();stage.style.flexDirection=FlexDirection.Row;stage.style.flexGrow=1;stage.style.marginTop=12;root.Add(stage);
                surface=new ViewerCardSurface(stage);surface.CardsRoot.style.width=600;surface.CardsRoot.style.flexShrink=0;surface.InspectionView.style.marginLeft=35;
                host=new ViewerSessionHost(surface,validated.Result,pipe.WaitForOwnerCloseAsync(cancellation.Token),true);
                if(decisions) {
                    surface.CardsRoot.style.width=460;surface.InspectionView.SetPresentation(CardPresentationMode.Full,260);surface.InspectionView.style.marginLeft=15;
                    stage.style.alignItems=Align.FlexStart;
                    var choices=new VisualElement();choices.style.width=320;choices.style.flexShrink=0;choices.style.marginLeft=20;stage.Add(choices);
                    decisionPanel=new ViewerDecisionPanel(choices,host);
                }
                var token=cancellation.Token;consuming=Task.Run(()=>{
                    while(!token.IsCancellationRequested && !host.Completion.IsCompleted) {
                        if(host.TryTake(out var update))using(update){if(update.Receive.Type=="snapshot")Interlocked.Increment(ref snapshots);else if(update.Receive.Type=="event")Interlocked.Increment(ref events);else if(decisions && update.Receive.Type=="ack")Interlocked.Increment(ref acknowledgements);else if(decisions && update.Receive.Type=="result")Interlocked.Increment(ref results);else{Interlocked.Exchange(ref unexpected,1);host.Cancel();}}
                        else Thread.Sleep(10);
                    }
                });
            }catch{Fail("SESSION_FIXTURE_START_FAILED");yield break;}
            double deadline=Time.realtimeSinceStartupAsDouble+20;
            while(!host.Completion.IsCompleted && (surface.CardsRoot.childCount!=2 || Volatile.Read(ref events)<1)) {
                host.Tick();decisionPanel?.Tick();if(Time.realtimeSinceStartupAsDouble>=deadline){Fail("SESSION_FIXTURE_READY_TIMEOUT");yield break;}yield return null;
            }
            host.Tick();decisionPanel?.Tick();
            if(host.Completion.IsCompleted || Volatile.Read(ref unexpected)!=0 || !host.Authenticated || surface.CardsRoot.childCount!=2 || !host.Inspect("fixture-0002")){Fail("SESSION_FIXTURE_START_FAILED");yield break;}
            if(decisions && (host.PresentedDecision==null || decisionPanel.Root.Q<Button>("decision-option-0")==null)){Fail("SESSION_FIXTURE_DECISION_NOT_MOUNTED");yield break;}
            status.text=decisions?"Connected. Choose an explicit public fixture option below.":"Connected. One public card and one concealed card; inspection only.";
            if(capture)yield return Capture("connected.png");
            if(!Report("ready","SESSION_FIXTURE_READY")){Application.Quit(1);yield break;}
            if(scripted && decisions) {
                // Explicit PUBLIC diagnostic script only, through the mounted UI callback.
                // Desktop/product launch never sets this fixture-only switch.
                var button=decisionPanel.Root.Q<Button>("decision-option-0");
                using(var input=NavigationSubmitEvent.GetPooled()){input.target=button;button.SendEvent(input);}
            }
            while(!host.Completion.IsCompleted) {
                host.Tick();decisionPanel?.Tick();
                if(decisions && !decisionReported && Volatile.Read(ref results)==1 && host.PresentedDecision==null) {
                    if(Volatile.Read(ref acknowledgements)!=2 || decisionPanel.Root.Q<Button>()!=null){Fail("SESSION_FIXTURE_DECISION_FAILED");yield break;}
                    status.text="Synthetic choice confirmed and fixture completed — not a live game.";
                    if(capture)yield return Capture("decision-complete.png");
                    if(!Report("decision","SESSION_FIXTURE_DECISION_COMPLETE")){Application.Quit(1);yield break;}decisionReported=true;
                }
                yield return null;
            }
            host.Tick();decisionPanel?.Tick();decisionPanel?.Dispose();host.Dispose();surface.Dispose();
            while(!consuming.IsCompleted)yield return null;
            bool cleared=document.rootVisualElement.Query<CardView>().ToList().Count==0;
            bool passed=host.Completion.Result.Code=="VIEWER_OWNER_ENDED" && host.Completion.Result.CleanupConfirmed && cleared && Volatile.Read(ref unexpected)==0 && consuming.Status==TaskStatus.RanToCompletion;
            status.text=passed?"Owner disconnected — viewer cleared.":"Fixture session stopped unexpectedly.";
            if(capture)yield return Capture("cleared.png");
            Application.Quit(Report(passed?"closed":"failed",passed?"SESSION_FIXTURE_OWNER_EOF":"SESSION_FIXTURE_STOP_FAILED",cleared)&&passed?0:1);
        }
        private IEnumerator Capture(string name)
        {
            var target=new RenderTexture(1280,720,24);Texture2D pixels=null;var previous=RenderTexture.active;
            try {
                target.Create();settings.targetTexture=target;for(int i=0;i<30;i++){host?.Tick();decisionPanel?.Tick();yield return null;}yield return new WaitForEndOfFrame();
                pixels=new Texture2D(1280,720,TextureFormat.RGBA32,false);RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1280,720),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(output,name),pixels.EncodeToPNG());
            }finally{settings.targetTexture=null;RenderTexture.active=previous;if(pixels!=null)Destroy(pixels);target.Release();Destroy(target);}
        }
        private void OnDestroy()
        {
            cancellation.Cancel();decisionPanel?.Dispose();host?.Dispose();surface?.Dispose();pipe?.Dispose();
            foreach(var task in new[]{reading,validated})task?.ContinueWith(done=>{if(done.Status==TaskStatus.RanToCompletion)done.Result?.Dispose();else _=done.Exception;},TaskScheduler.Default);
            consuming?.ContinueWith(done=>{_=done.Exception;},TaskScheduler.Default);if(settings!=null)Destroy(settings);cancellation.Dispose();
        }
    }
}
