using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Normal authenticated gameplay surface. No fixture decisions or native/root deck data.
    public sealed class LiveGameScene : MonoBehaviour
    {
        private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private ViewerBootstrapPipe pipe;private ViewerSessionHost host;private ViewerCardSurface surface;private ViewerDecisionPanel panel;
        private PanelSettings settings;private UIDocument document;private Task<ViewerBootstrap> reading;private Task consuming;
        private string[] untappedLandIds=new string[0],counterBallistaIds=new string[0];
        private ProjectedDecisionFrame latest;private string output;private bool quit,ready,userRequested;private int snapshots,confirmed,uncertain,availableLands,availableCreatures;
        private IGameplayPresentation presentation;private Func<VisualElement,IGameplayPresentation> presentationFactory=root=>new TableGameplayPresentation(root);private LiveGameAcceptanceDriver acceptance;
        public void SetPresentationFactory(Func<VisualElement,IGameplayPresentation> factory){if(document!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_STARTED");presentationFactory=factory??throw new ArgumentNullException(nameof(factory));}
        private void Write(string name,JObject value){string temporary=Path.Combine(output,name+".tmp");File.WriteAllText(temporary,value.ToString());File.Move(temporary,Path.Combine(output,name+".json"));}
        private IEnumerator Start()
        {
            output=ArtworkFixtureScene.Argument("-manaforgeLiveGame");
            try{Directory.CreateDirectory(output);pipe=ViewerBootstrapPipe.FromStandardInput();reading=pipe.ReadBootstrapAsync(10000,cancellation.Token);}catch{Application.Quit(1);yield break;}
            while(!reading.IsCompleted)yield return null;
            if(reading.Status!=TaskStatus.RanToCompletion){Application.Quit(1);yield break;}
            try{
                settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");settings.scaleMode=PanelScaleMode.ScaleWithScreenSize;settings.referenceResolution=new Vector2Int(1280,720);
                document=gameObject.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.flexGrow=1;root.style.paddingLeft=20;root.style.paddingTop=15;root.style.backgroundColor=new Color(.025f,.055f,.075f);
                var leave=new Button(()=>{userRequested=true;quit=true;}){text="Return to Manaforge"};root.Add(leave);
                presentation=presentationFactory(root);surface=presentation.Surface;
                host=new ViewerSessionHost(surface,reading.Result,pipe.WaitForOwnerCloseAsync(cancellation.Token),false);presentation.Bind(host);panel=presentation.Decisions;
                if(ArtworkFixtureScene.Argument("-manaforgeGameAcceptance")=="1")acceptance=new LiveGameAcceptanceDriver();
                var token=cancellation.Token;consuming=Task.Run(()=>{
                    while(!token.IsCancellationRequested && !host.Completion.IsCompleted){if(host.TryTake(out var update))using(update){
                        if(update.Receive.Type=="snapshot" || update.Receive.Type=="result"){if(acceptance!=null){var snapshot=JObject.Parse(update.Packet.ReadJson())["body"]["snapshot"];int lands=0,creatures=0;var landIds=new System.Collections.Generic.List<string>();var ballistaIds=new System.Collections.Generic.List<string>();foreach(var card in snapshot["objects"]){if((string)card["controller_id"]==update.Decision.Context.ViewerId && (string)card["zone"]=="battlefield"){if((bool?)card["tapped"]==false && ((string)card["characteristics"]?["type_line"]??"").Contains("Land")){lands++;landIds.Add((string)card["object_id"]);}if((string)card["characteristics"]?["name"]=="Walking Ballista" && card["counters"] is JArray counters)foreach(var counter in counters)if((string)counter[0]=="+1/+1" && (long)counter[1]>0)ballistaIds.Add((string)card["object_id"]);if(((string)card["characteristics"]?["type_line"]??"").Contains("Creature"))creatures++;}}Volatile.Write(ref untappedLandIds,landIds.ToArray());Volatile.Write(ref counterBallistaIds,ballistaIds.ToArray());Volatile.Write(ref availableLands,lands);Volatile.Write(ref availableCreatures,creatures);}Volatile.Write(ref latest,update.Decision);Interlocked.Increment(ref snapshots);}
                        if(update.Receive.Receipt?.State==CommandState.Confirmed)Interlocked.Increment(ref confirmed);
                        if(update.Receive.Receipt?.State==CommandState.Uncertain)Interlocked.Increment(ref uncertain);
                    }else Thread.Sleep(10);}
                });
            }catch{Application.Quit(1);yield break;}
            while(!quit && !host.Completion.IsCompleted){
                host.Tick();panel.Tick();var frame=Volatile.Read(ref latest);
                if(frame!=null && host.HasPresentedRevision(frame.Context.Revision)){
                    if(!ready){ready=true;Write("game-ready",new JObject{["live_game_version"]=1,["authenticated"]=host.Authenticated});}
                    presentation.Present(frame);
                    if(acceptance!=null){acceptance.SetAvailableLands(Volatile.Read(ref availableLands),Volatile.Read(ref availableCreatures),Volatile.Read(ref untappedLandIds),Volatile.Read(ref counterBallistaIds));quit=frame.UnsupportedFields.Contains("decision") || acceptance.Tick(host,panel,frame);}
                }
                yield return null;
            }
            Write("game-closing",new JObject{["live_game_version"]=1,["requested"]=quit});var final=Volatile.Read(ref latest);host.Cancel();host.Tick();host.Dispose();presentation.Dispose();while(!consuming.IsCompleted)yield return null;
            bool cleared=document.rootVisualElement.Query<CardView>().ToList().Count==0;Write("game-closed",new JObject{["live_game_version"]=1,["outcome"]=final?.Result,["user_requested"]=userRequested,["snapshots"]=Volatile.Read(ref snapshots),["confirmed"]=Volatile.Read(ref confirmed),["uncertain"]=Volatile.Read(ref uncertain),["viewer_cleared"]=cleared,["cleanup_confirmed"]=host.Completion.Result.CleanupConfirmed});
            Application.Quit(cleared && host.Completion.Result.CleanupConfirmed?0:1);
        }
        private void OnDestroy(){cancellation.Cancel();host?.Dispose();presentation?.Dispose();pipe?.Dispose();reading?.ContinueWith(done=>{if(done.Status==TaskStatus.RanToCompletion)done.Result?.Dispose();else _=done.Exception;},TaskScheduler.Default);consuming?.ContinueWith(done=>{_=done.Exception;},TaskScheduler.Default);if(settings!=null)Destroy(settings);cancellation.Dispose();}
    }
}
