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
        private int reviewResolution;private bool resolutionPending,resolutionRestored;private Vector2Int reviewOriginalSize;private readonly JArray resolutionEvidence=new JArray();
        private long captureRevision=-1;private float captureReady;private readonly System.Collections.Generic.HashSet<string> captures=new System.Collections.Generic.HashSet<string>();
        private readonly System.Collections.Generic.HashSet<string> artworkProof=new System.Collections.Generic.HashSet<string>();
        private readonly JArray artworkEvidence=new JArray();
        private long artworkProgressRevision=-1;
        private IGameplayPresentation presentation;private Func<VisualElement,IGameplayPresentation> presentationFactory=root=>new ArenaGameplayPresentation(root);private LiveGameAcceptanceDriver acceptance;private SpatialInputAcceptance spatialAcceptance;
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
                document=gameObject.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.flexGrow=1;root.style.backgroundColor=new Color(.025f,.055f,.075f);
                var leave=new Button(()=>{userRequested=true;quit=true;}){text="Return to Manaforge"};leave.name="game-leave";leave.style.position=Position.Absolute;leave.style.left=12;leave.style.top=10;leave.style.backgroundColor=new Color(.08f,.09f,.11f,.9f);leave.style.color=new Color(.94f,.88f,.76f);root.Add(leave);
                GameplayTheme.Attach(root);GameplayTheme.Button(leave);leave.style.backgroundColor=StyleKeyword.Null;leave.style.color=StyleKeyword.Null;presentation=presentationFactory(root);leave.BringToFront();surface=presentation.Surface;
                host=new ViewerSessionHost(surface,reading.Result,pipe.WaitForOwnerCloseAsync(cancellation.Token),false,allowIdleWait:true);presentation.Bind(host);panel=presentation.Decisions;
                bool gameAcceptance=ArtworkFixtureScene.Argument("-manaforgeGameAcceptance")=="1";
                if(gameAcceptance || ArtworkFixtureScene.Argument("-manaforgeRulesTextProof")=="1"){acceptance=new LiveGameAcceptanceDriver();if(gameAcceptance && presentation is ArenaGameplayPresentation)spatialAcceptance=new SpatialInputAcceptance(panel,surface,host);}
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
                    if(ArtworkFixtureScene.Argument("-manaforgeArtworkProof")=="1" && frame.Result==null && frame.Decision==null && frame.Actions.Count==0) {yield return null;continue;}
                    if(ArtworkFixtureScene.Argument("-manaforgeRulesTextProof")=="1") {
                        ProjectedCard proofCard=null;
                        surface.VisitPresented((card,view)=>{if(proofCard==null && !card.Hidden && card.Zone=="hand")proofCard=card;});
                        if(proofCard!=null && presentation is ArenaGameplayPresentation proofArena) {
                            // Opt-in public-deck screenshot proof; never submits a game command.
                            float deadline=Time.realtimeSinceStartup+10;
                            while(surface.ExpectedArtworkCount>surface.PresentedArtworkCount && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                            proofArena.InspectCard(proofCard.ObjectId);yield return null;yield return null;
                            var label=surface.InspectionView.Q<Label>("rules");var symbols=surface.InspectionView.Q<RulesTextView>();
                            var viewport=surface.InspectionView.Q<ScrollView>("rules-scroll").contentViewport;
                            var textElement=symbols.SymbolCount>0?(VisualElement)symbols:label;
                            bool visible=textElement.resolvedStyle.display==DisplayStyle.Flex && textElement.worldBound.width>20 && textElement.worldBound.height>5 && textElement.worldBound.Overlaps(viewport.worldBound);
                            Write("rules-text-proof",new JObject{["authenticated"]=host.Authenticated,["name"]=proofCard.Characteristics.Name,["engine_rules"]=ViewerCardSurface.DisplayRules(proofCard.Characteristics.CurrentAbilities,proofCard.Characteristics.EngineViewText),["displayed_rules"]=label.text,["mana_cost"]=surface.InspectionView.Q<ManaCostView>().Cost,["visible"]=visible});
                            yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(output,"rules-text-proof.png"));
                            yield return new WaitForSecondsRealtime(.3f);userRequested=true;quit=true;
                        }
                    }
                    if(!quit && acceptance!=null && CaptureReady(frame)){acceptance.SetAvailableLands(Volatile.Read(ref availableLands),Volatile.Read(ref availableCreatures),Volatile.Read(ref untappedLandIds),Volatile.Read(ref counterBallistaIds));quit=frame.UnsupportedFields.Contains("decision") || acceptance.Tick(host,panel,frame);}
                }
                yield return null;
            }
            host.Tick(); // Clear revoked viewer resources before the text-only result fanfare.
            var final=Volatile.Read(ref latest);
            if(final?.Result!=null){presentation.Present(final);yield return new WaitForEndOfFrame();if(acceptance!=null && ArtworkFixtureScene.Argument("-manaforgeNoCapture")!="1")ScreenCapture.CaptureScreenshot(Path.Combine(output,"result.png"));if(acceptance!=null)yield return new WaitForSecondsRealtime(.3f);else while(!quit){host.Tick();yield return null;}}
            Write("game-closing",new JObject{["live_game_version"]=1,["requested"]=quit});
            if(spatialAcceptance!=null){Write("board-input-proof",new JObject{["card_keyboard_inputs"]=spatialAcceptance.Inputs});spatialAcceptance.Dispose();}
            host.Cancel();host.Tick();host.Dispose();presentation.Dispose();while(!consuming.IsCompleted)yield return null;
            bool cleared=document.rootVisualElement.Query<CardView>().ToList().Count==0;Write("game-closed",new JObject{["live_game_version"]=1,["outcome"]=final?.Result,["user_requested"]=userRequested,["snapshots"]=Volatile.Read(ref snapshots),["confirmed"]=Volatile.Read(ref confirmed),["uncertain"]=Volatile.Read(ref uncertain),["viewer_cleared"]=cleared,["cleanup_confirmed"]=host.Completion.Result.CleanupConfirmed});
            Application.Quit(cleared && host.Completion.Result.CleanupConfirmed?0:1);
        }
        // Public-deck acceptance evidence only; no capture or pacing changes in normal play.
        private bool CaptureReady(ProjectedDecisionFrame frame)
        {
            if(ArtworkFixtureScene.Argument("-manaforgeNoCapture")=="1")return true;
            if(captureRevision!=frame.Context.Revision){captureRevision=frame.Context.Revision;captureReady=Time.unscaledTime+.35f;return false;}
            if(Time.unscaledTime<captureReady)return false;
            if(ArtworkFixtureScene.Argument("-manaforgeArtworkProof")=="1") {
                if(artworkProgressRevision!=frame.Context.Revision) {
                    artworkProgressRevision=frame.Context.Revision;
                    File.WriteAllText(Path.Combine(output,"artwork-progress.json"),new JObject{["revision"]=frame.Context.Revision,["prompt"]=frame.Decision?.Prompt,["family"]=frame.Decision?.Family,["actions"]=new JArray(frame.Actions.Select(a=>a.Label)),["completed"]=new JArray(artworkProof),["expected"]=surface.ExpectedArtworkCount,["presented"]=surface.PresentedArtworkCount}.ToString());
                    ScreenCapture.CaptureScreenshot(Path.Combine(output,"artwork-progress.png"));
                }
                if(surface.ExpectedArtworkCount>surface.PresentedArtworkCount && Time.unscaledTime<captureReady+15)return false;
                bool recorded=false;
                surface.VisitPresented((card,view)=>{
                    if(card.Hidden || card.Zone!="battlefield" || view.Artwork==null)return;
                    string category=card.Characteristics?.Name=="Goblin" || card.Characteristics?.Name=="Goblin Token"?"token":card.OwnerId!=frame.Context.ViewerId?"opponent":card.Characteristics?.Name=="Mountain"?"mountain":null;
                    if(category!=null && artworkProof.Add(category)) {
                        artworkEvidence.Add(new JObject{["category"]=category,["name"]=card.Characteristics.Name,["printing_id"]=card.Printing?.PrintingId,["oracle_id"]=card.Printing?.OracleId});
                        ScreenCapture.CaptureScreenshot(Path.Combine(output,"artwork-"+category+".png"));recorded=true;
                    }
                });
                if(recorded){captureReady=Time.unscaledTime+.3f;return false;}
                if(artworkProof.Count==3){Write("artwork-proof",new JObject{["mountain"]=true,["opponent"]=true,["token"]=true,["authenticated"]=host.Authenticated,["cards"]=artworkEvidence});userRequested=true;quit=true;return false;}
                return true;
            }
            if(!(frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase) && document.rootVisualElement.Query<VisualElement>(className:"library-flight").ToList().Count>0 && captures.Add("draw")){ScreenCapture.CaptureScreenshot(Path.Combine(output,"draw.png"));captureReady=Time.unscaledTime+.15f;return false;}
            string state=frame.Result!=null?"result":frame.Combat.Count>0?"combat":(frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase)?"opening":frame.Actions.Any(a=>a.Kind=="cast")?"casting":"priority";
            int permanents=0;surface.VisitPresented((card,view)=>{if(card.Zone=="battlefield")permanents++;});
            if(state=="priority" && permanents>=3)state="battlefield";
            if(captures.Add(state)){ScreenCapture.CaptureScreenshot(Path.Combine(output,state+".png"));captureReady=Time.unscaledTime+.15f;return false;}
            if(captures.Contains("battlefield") && !CaptureDesktopSizes())return false;
            if(captures.Contains("battlefield") && presentation is ArenaGameplayPresentation arena){
                if(captures.Add("library-browser")){arena.BrowsePublicZone("library",frame.Context.ViewerId);ScreenCapture.CaptureScreenshot(Path.Combine(output,"library-browser.png"));captureReady=Time.unscaledTime+.2f;return false;}
                if(captures.Add("exile-browser")){arena.BrowsePublicZone("exile",frame.Context.ViewerId);ScreenCapture.CaptureScreenshot(Path.Combine(output,"exile-browser.png"));captureReady=Time.unscaledTime+.2f;return false;}
                arena.ClosePublicZone();
                CardView review=null;string id=null;surface.VisitPresented((card,view)=>{if(review==null && !card.Hidden && card.Zone=="battlefield"){review=view;id=card.ObjectId;}});
                if(review!=null && captures.Add("hover")){review.Focus();ScreenCapture.CaptureScreenshot(Path.Combine(output,"hover.png"));captureReady=Time.unscaledTime+.2f;return false;}
                if(id!=null && captures.Add("inspection")){arena.InspectCard(id);ScreenCapture.CaptureScreenshot(Path.Combine(output,"inspection.png"));captureReady=Time.unscaledTime+.2f;return false;}
                arena.CloseInspection();
                string publicZone=null,zoneOwner=null;
                surface.VisitPresented((card,view)=>{if(publicZone==null && !card.Hidden && card.Zone=="graveyard"){publicZone=card.Zone;zoneOwner=card.OwnerId;}});
                if(publicZone!=null && !captures.Contains("public-zone") && arena.BrowsePublicZone(publicZone,zoneOwner)){
                    captures.Add("public-zone");ScreenCapture.CaptureScreenshot(Path.Combine(output,"public-zone.png"));captureReady=Time.unscaledTime+.2f;return false;
                }
                arena.ClosePublicZone();
            }
            return true;
        }
        // Real player framebuffer captures at desktop sizes; normal play never enters this path.
        private bool CaptureDesktopSizes()
        {
            var sizes=new[]{new Vector2Int(1366,768),new Vector2Int(1920,1080),new Vector2Int(2560,1440)};
            if(reviewResolution<sizes.Length){
                var target=sizes[reviewResolution];
                if(!resolutionPending){if(reviewResolution==0)reviewOriginalSize=new Vector2Int(Screen.width,Screen.height);Screen.SetResolution(target.x,target.y,FullScreenMode.Windowed);resolutionPending=true;captureReady=Time.unscaledTime+.5f;return false;}
                string filename="battlefield-"+Screen.width+"x"+Screen.height+".png";
                ScreenCapture.CaptureScreenshot(Path.Combine(output,filename));resolutionEvidence.Add(new JObject{["requested_width"]=target.x,["requested_height"]=target.y,["actual_width"]=Screen.width,["actual_height"]=Screen.height,["file"]=filename});
                reviewResolution++;resolutionPending=false;captureReady=Time.unscaledTime+.2f;return false;
            }
            if(!resolutionRestored){Screen.SetResolution(reviewOriginalSize.x,reviewOriginalSize.y,FullScreenMode.Windowed);resolutionRestored=true;Write("resolution-proof",new JObject{["captures"]=resolutionEvidence});captureReady=Time.unscaledTime+.4f;return false;}
            return true;
        }
        private void OnDestroy(){spatialAcceptance?.Dispose();cancellation.Cancel();host?.Dispose();presentation?.Dispose();pipe?.Dispose();reading?.ContinueWith(done=>{if(done.Status==TaskStatus.RanToCompletion)done.Result?.Dispose();else _=done.Exception;},TaskScheduler.Default);consuming?.ContinueWith(done=>{_=done.Exception;},TaskScheduler.Default);if(settings!=null)Destroy(settings);cancellation.Dispose();}
    }
}
