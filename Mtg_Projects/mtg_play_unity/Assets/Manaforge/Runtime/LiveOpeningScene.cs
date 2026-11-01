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
        private PanelSettings settings;private UIDocument document;private string output;private Label status;private Label note;private OpeningCardFocus cardFocus;private OpeningButtonGlow buttonGlow;
        private long snapshotRevision=-1;private int snapshots,acks,confirmedReceipts,uncertainReceipts;private bool capture,choiceReported,land,priority,creature,artwork,backdrop,requestedBackdrop,mulliganControls,buttonSkins,continuePriority,followupPresented,observeResolution,battlefieldPresented,postResolutionPass;
        private bool OpeningLayout=>!land && !creature;
        private float fanWidth=-1;private int fanCount=-1,fanArtwork=-1;private long fanRevision=-1;
        private void PresentOpening()
        {
            if(!OpeningLayout)return;float width=surface.CardsRoot.resolvedStyle.width;int count=surface.CardsRoot.childCount;long revision=host.PresentedDecision?.Frame.Context.Revision??-1;
            int images=surface.PresentedArtworkCount;
            if(float.IsNaN(width) || width<=0 || width==fanWidth && count==fanCount && revision==fanRevision && images==fanArtwork)return;
            if(cardFocus==null)OpeningHandFan.Present(surface.CardsRoot);else cardFocus.PresentHand();
            if(artwork)foreach(var card in surface.CardsRoot.Query<CardView>().ToList())card.Q<Label>("status").style.display=DisplayStyle.None;
            fanWidth=width;fanCount=count;fanRevision=revision;fanArtwork=images;
        }
        private Button InputButton(string name)=>priority?panel.Root.Query<Button>().ToList().Find(button=>button.text=="Pass priority"):panel.Root.Q<Button>(name);
        private void LimitActions()
        {
            if(!land)return;
            foreach(var button in panel.Root.Query<Button>().ToList())if(button.name.StartsWith("decision-action-"))button.style.display=(priority?button.text=="Pass priority":button.text!="Pass priority")?DisplayStyle.Flex:DisplayStyle.None;
        }
        private bool Report(string name,bool cleared=false)
        {
            try{var value=new JObject{["probe_version"]=1,["live_opening"]=true,["snapshot_count"]=Volatile.Read(ref snapshots),["ack_count"]=Volatile.Read(ref acks),["confirmed_receipt_count"]=Volatile.Read(ref confirmedReceipts),["uncertain_receipt_count"]=Volatile.Read(ref uncertainReceipts),["post_resolution_priority_presented"]=postResolutionPass && battlefieldPresented,["followup_priority_presented"]=followupPresented,["battlefield_observation_presented"]=battlefieldPresented,["viewer_cleared"]=cleared,["arena_button_glows"]=buttonGlow?.Count??0,["arena_button_skins"]=buttonSkins,["mulligan_controls"]=mulliganControls,["arena_backdrop_resource"]=backdrop?ArenaOpeningBackdrop.ResourceName:null,["arena_backdrop"]=backdrop,["artwork_count"]=surface?.PresentedArtworkCount??0};
                string path=Path.Combine(output,name+".json");File.WriteAllText(path+".tmp",value.ToString());File.Move(path+".tmp",path);return true;}catch{return false;}
        }
        private void Fail(){host?.Dispose();Report("failed");Application.Quit(1);}
        private IEnumerator Start()
        {
            output=ArtworkFixtureScene.Argument("-manaforgeLiveOpening");capture=ArtworkFixtureScene.Argument("-manaforgeLiveCapture")=="1";
            priority=ArtworkFixtureScene.Argument("-manaforgeLivePriority")=="1";
            creature=ArtworkFixtureScene.Argument("-manaforgeLiveCreature")=="1";
            continuePriority=ArtworkFixtureScene.Argument("-manaforgeLiveContinuePriority")=="1";
            if(continuePriority && !creature){Application.Quit(1);yield break;}
            observeResolution=ArtworkFixtureScene.Argument("-manaforgeLiveObserveResolution")=="1";
            if(observeResolution && !continuePriority){Application.Quit(1);yield break;}
            postResolutionPass=ArtworkFixtureScene.Argument("-manaforgeLivePostResolutionPass")=="1";
            if(postResolutionPass && !observeResolution){Application.Quit(1);yield break;}
            land=priority || ArtworkFixtureScene.Argument("-manaforgeLiveLand")=="1";
            try{Directory.CreateDirectory(output);pipe=ViewerBootstrapPipe.FromStandardInput();reading=pipe.ReadBootstrapAsync(5000,cancellation.Token);}catch{Fail();yield break;}
            while(!reading.IsCompleted)yield return null;
            if(reading.Status!=TaskStatus.RanToCompletion || reading.Result.SessionId!="live-opening" || reading.Result.ViewerId!="human"){Fail();yield break;}
            artwork=reading.Result.ArtworkDirectory!=null;
            requestedBackdrop=ArtworkFixtureScene.Argument("-manaforgeArenaBackdrop")=="1";
            if(requestedBackdrop && (!artwork || !OpeningLayout)){Fail();yield break;}
            try{
                settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");settings.scaleMode=PanelScaleMode.ScaleWithScreenSize;settings.referenceResolution=new Vector2Int(1280,720);
                document=gameObject.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.flexGrow=1;root.style.paddingLeft=20;root.style.paddingTop=15;root.style.backgroundColor=new Color(.025f,.055f,.075f);
                var title=new Label(creature?"LIVE XMAGE — CASTING ABILITY":priority?"LIVE XMAGE — PRIORITY PASS":land?"LIVE XMAGE — FIRST LAND":"LIVE XMAGE — HUMAN vs AI OPENING");title.style.fontSize=23;title.style.color=Color.white;root.Add(title);
                status=new Label("Connecting to the owned Java gateway…");status.style.color=Color.white;root.Add(status);
                note=new Label(postResolutionPass?"Public Memnite/Forest decks. Choose the ability, then two explicit priority passes. Final pass remains uncertain; no full match.":continuePriority?"Public Memnite/Forest decks. Choose the casting ability, then one priority pass. Stack contents unavailable; no full match.":creature?"Public Memnite/Forest decks. Diagnostic card click completed. Choose the casting ability; Java checks the stack entry.":priority?"Public Forest decks. Diagnostic setup completed. One explicit priority pass; no full match.":land?"Public Forest decks. Diagnostic pregame/keep already completed. One land action only; no full match.":artwork?"Public Forest/Ornithopter decks. Verified offline artwork. Current rules / tap state unavailable; one opening decision only.":"Public Forest/Memnite decks. Opening decision only; artwork cache and later gameplay are not connected.");note.style.color=requestedBackdrop?new Color(.9f,.9f,.9f):Color.gray;root.Add(note);
                var stage=new VisualElement();stage.style.flexDirection=FlexDirection.Row;stage.style.flexGrow=1;stage.style.marginTop=10;root.Add(stage);
                surface=new ViewerCardSurface(stage);surface.CardsRoot.style.width=720;surface.CardsRoot.style.flexShrink=0;surface.InspectionView.SetPresentation(CardPresentationMode.Full,210);
                host=new ViewerSessionHost(surface,reading.Result,pipe.WaitForOwnerCloseAsync(cancellation.Token),false);
                var choices=new VisualElement();choices.style.width=290;choices.style.flexShrink=0;stage.Add(choices);panel=new ViewerDecisionPanel(choices,host);
                if(OpeningLayout){
                    title.text="Opening Hand";title.style.fontSize=38;title.style.unityTextAlign=TextAnchor.MiddleCenter;CardTypography.Apply(title,CardTextRole.Title);
                    root.style.paddingRight=20;stage.style.marginTop=60;stage.style.position=Position.Relative;stage.style.backgroundColor=requestedBackdrop?Color.clear:new Color(0,0,0,.3f);
                    surface.CardsRoot.style.position=Position.Absolute;surface.CardsRoot.style.left=0;surface.CardsRoot.style.top=0;surface.CardsRoot.style.width=Length.Percent(100);surface.CardsRoot.style.height=430;
                    surface.InspectionView.style.position=Position.Absolute;surface.InspectionView.style.right=8;surface.InspectionView.style.top=0;surface.InspectionView.style.display=DisplayStyle.None;
                    choices.style.position=Position.Absolute;choices.style.left=0;choices.style.bottom=OpeningMulliganControls.BottomInset;choices.style.width=Length.Percent(100);
                    panel.Root.style.backgroundColor=Color.clear;
                    var prompt=panel.Root.Q<Label>("decision-prompt");prompt.style.unityTextAlign=TextAnchor.MiddleCenter;CardTypography.Apply(prompt,CardTextRole.Title);
                    panel.Root.Q<Label>("decision-status").style.unityTextAlign=TextAnchor.MiddleCenter;
                    var controls=panel.Root.Q<VisualElement>("decision-controls");controls.style.flexDirection=FlexDirection.Row;controls.style.justifyContent=Justify.Center;
                }
                var token=cancellation.Token;consuming=Task.Run(()=>{while(!token.IsCancellationRequested && !host.Completion.IsCompleted){if(host.TryTake(out var update))using(update){if(update.Receive.Type=="snapshot"){Interlocked.Exchange(ref snapshotRevision,update.Decision?.Context.Revision??-1);Interlocked.Increment(ref snapshots);}if(update.Receive.Type=="ack"){Interlocked.Increment(ref acks);if(update.Receive.Receipt?.State==CommandState.Confirmed)Interlocked.Increment(ref confirmedReceipts);if(update.Receive.Receipt?.State==CommandState.Uncertain)Interlocked.Increment(ref uncertainReceipts);}}else Thread.Sleep(10);}});
            }catch{Fail();yield break;}
            double deadline=Time.realtimeSinceStartupAsDouble+20;
            string control=land?"decision-action-0":"decision-option-0";
            while(!host.Completion.IsCompleted && ((!land && !creature && surface.CardsRoot.childCount!=7) || InputButton(control)==null || artwork && (surface.ExpectedArtworkCount==0 || surface.PresentedArtworkCount<surface.ExpectedArtworkCount))){
                host.Tick();panel.Tick();if(Time.realtimeSinceStartupAsDouble>=deadline){Fail();yield break;}yield return null;
            }
            if(host.Completion.IsCompleted || !host.Authenticated){Fail();yield break;}
            LimitActions();
            if(OpeningLayout){
                var question=panel.Root.Q<Label>("decision-prompt");question.text=OpeningHandFan.PlainPrompt(question.text);
                foreach(var button in panel.Root.Query<Button>().ToList()){
                    button.style.width=OpeningMulliganControls.ButtonWidth;button.style.height=OpeningMulliganControls.ButtonHeight;button.style.fontSize=24;button.style.marginLeft=OpeningMulliganControls.ButtonMargin;button.style.marginRight=OpeningMulliganControls.ButtonMargin;button.style.paddingTop=0;button.style.paddingBottom=0;
                    button.style.borderTopLeftRadius=button.style.borderTopRightRadius=button.style.borderBottomLeftRadius=button.style.borderBottomRightRadius=20;
                    button.style.backgroundColor=button.name=="decision-option-0"?new Color(.22f,.25f,.85f):new Color(.95f,.36f,.08f);
                }
                mulliganControls=OpeningMulliganControls.Apply(panel.Root,surface.CardsRoot.childCount);
                if(mulliganControls)buttonSkins=OpeningMulliganControls.ApplyLocalSkins(panel.Root);
                if(buttonSkins)buttonGlow=OpeningButtonGlow.AttachLocal(panel.Root);
                PresentOpening();cardFocus=new OpeningCardFocus(surface.CardsRoot);
            }else foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
            var inspect=new VisualElement();inspect.style.flexDirection=FlexDirection.Row;document.rootVisualElement.Insert(3,inspect);int count=0;
            foreach(string objectId in surface.PresentedObjectIds()){string id=objectId;inspect.Add(new Button(()=>{if(OpeningLayout)surface.InspectionView.style.display=DisplayStyle.Flex;host.Inspect(id);}){text="Inspect "+(++count)});}
            if(OpeningLayout){
                OpeningDiagnostics.Attach(document.rootVisualElement,status,note,inspect);
                // Move the engine-owned prompt after mapping, retaining its live updates and clearing.
                var headerPrompt=panel.Root.Q<Label>("decision-prompt");
                headerPrompt.style.fontSize=21;headerPrompt.style.color=new Color(.88f,.88f,.88f);
                headerPrompt.style.marginTop=8;headerPrompt.style.marginBottom=0;
                document.rootVisualElement.Insert(1,headerPrompt);
            }
            status.text=creature?"Connected to real XMage. Select the offered casting ability.":priority?"Connected to real XMage. Select Pass priority to yield this decision.":land?"Connected to real XMage. Select an offered Play land action.":"Connected to real XMage. Inspect your opening hand, then choose whether to mulligan.";
            if(requestedBackdrop){backdrop=ArenaOpeningBackdrop.AttachLocal(document.rootVisualElement);if(!backdrop){Fail();yield break;}}
            if(capture){yield return Capture("connected.png");if(cardFocus!=null){cardFocus.Show(surface.CardsRoot.Q<CardView>());yield return Capture("focused.png");cardFocus.Show(null);}}if(!Report("ready")){Application.Quit(1);yield break;}
            if(ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1"){
                // Opt-in public-deck acceptance script through the actual mounted UI callback.
                var button=InputButton(control);using(var input=NavigationSubmitEvent.GetPooled()){input.target=button;button.SendEvent(input);}
            }
            while(!host.Completion.IsCompleted){
                host.Tick();panel.Tick();buttonGlow?.Refresh();
                PresentOpening();
                cardFocus?.RefreshBounds();
                if(continuePriority && !followupPresented && Volatile.Read(ref snapshots)>=2){
                    var pass=panel.Root.Query<Button>().ToList().Find(button=>button.text=="Pass priority");
                    if(pass!=null && pass.enabledInHierarchy && host.PresentedDecision?.CanSubmit==true){
                        followupPresented=true;inspect.Clear();
                        foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                        status.text="Casting ability confirmed. Choose Pass priority; the next outcome remains unconfirmed.";
                        if(capture)yield return Capture("priority.png");if(!Report("priority-ready")){Application.Quit(1);yield break;}
                        if(ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=pass;pass.SendEvent(input);}
                    }
                }
                if(observeResolution && !battlefieldPresented && Volatile.Read(ref snapshots)==3 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    var buttons=panel.Root.Query<Button>().ToList();var postPass=buttons.Find(button=>button.text=="Pass priority");
                    if(postResolutionPass?(buttons.Count!=1 || postPass==null || !postPass.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || buttons.Count!=0)){Fail();yield break;}
                    battlefieldPresented=true;inspect.Clear();
                    foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text=postResolutionPass?"The prior pass is confirmed and the spell source is on the battlefield. Choose the next Pass priority.":"The verified spell source is now on the battlefield. Read-only observation; the exact priority pass is confirmed.";
                    if(capture)yield return Capture("battlefield.png");if(!Report("battlefield-ready")){Application.Quit(1);yield break;}
                    if(postResolutionPass && ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=postPass;postPass.SendEvent(input);}
                }
                if(!choiceReported && Volatile.Read(ref acks)>=(postResolutionPass?6:continuePriority?4:2) && (!observeResolution || battlefieldPresented)){
                    buttonGlow?.Dispose();buttonGlow=null;cardFocus?.Dispose();cardFocus=null;host.Cancel();host.Tick();panel.Tick();inspect.Clear();
                    status.text=postResolutionPass?"Post-resolution priority pass submitted; its outcome is uncertain. Viewer cleared; this test ends here.":observeResolution?"Casting ability and exact priority pass confirmed; battlefield observed. Viewer cleared; this test ends here.":continuePriority?"Casting ability confirmed; next priority pass submitted. Pass outcome uncertain. Viewer cleared; this test ends here.":creature?"Casting ability submitted; native Memnite stack entry observed. Viewer cleared; this test ends here.":priority?"Priority pass submitted to XMage; engine advanced. Viewer cleared; this test ends here.":"Choice submitted to XMage. Next-state support ends here; viewer cleared. No confirmed result is claimed.";
                    if(capture)yield return Capture("choice.png");if(!Report("choice",true)){Application.Quit(1);yield break;}choiceReported=true;
                }
                yield return null;
            }
            buttonGlow?.Dispose();buttonGlow=null;cardFocus?.Dispose();cardFocus=null;host.Tick();panel.Dispose();host.Dispose();surface.Dispose();while(!consuming.IsCompleted)yield return null;
            bool cleared=document.rootVisualElement.Query<CardView>().ToList().Count==0;
            Report("closed",cleared);Application.Quit(cleared && host.Completion.Result.CleanupConfirmed?0:1);
        }
        private IEnumerator Capture(string name)
        {
            var target=new RenderTexture(1280,720,24);Texture2D pixels=null;var previous=RenderTexture.active;
            try{target.Create();settings.targetTexture=target;for(int i=0;i<20;i++)yield return null;yield return new WaitForEndOfFrame();pixels=new Texture2D(1280,720,TextureFormat.RGBA32,false);RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1280,720),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(output,name),pixels.EncodeToPNG());}
            finally{settings.targetTexture=null;RenderTexture.active=previous;if(pixels!=null)Destroy(pixels);target.Release();Destroy(target);}
        }
        private void OnDestroy(){buttonGlow?.Dispose();cardFocus?.Dispose();cancellation.Cancel();panel?.Dispose();host?.Dispose();surface?.Dispose();pipe?.Dispose();reading?.ContinueWith(done=>{if(done.Status==TaskStatus.RanToCompletion)done.Result?.Dispose();else _=done.Exception;},TaskScheduler.Default);consuming?.ContinueWith(done=>{_=done.Exception;},TaskScheduler.Default);if(settings!=null)Destroy(settings);cancellation.Dispose();}
    }
}
