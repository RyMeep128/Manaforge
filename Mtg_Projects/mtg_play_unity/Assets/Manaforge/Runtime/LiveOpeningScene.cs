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
        private long snapshotRevision=-1;private int snapshots,acks,confirmedReceipts,uncertainReceipts;private bool capture,choiceReported,land,priority,creature,artwork,backdrop,requestedBackdrop,mulliganControls,buttonSkins,continuePriority,followupPresented,observeResolution,battlefieldPresented,postResolutionPass,phasePresented,combatFinish,combatResultPresented,combatPriority,combatPriorityResultPresented,selectAttacker,attackAssignmentPresented;private string attackAssignmentSummary;private bool finishSelectedAttack,declaredAttackPresented,declaredPriority,postDeclaredPriorityPresented;private int combatBlockerCount=-1;private bool combatDamage,combatDamagePresented;private long defenderLife=-1,damageLifeBefore=-1,damageLifeAfter=-1;private bool completeCombat,combatCleanupPresented;private int combatGroupCount=-1;private string combatDefenderId,blockerSummary;private bool blockedCombat,blockedDamage,blockedDamagePresented,loopTurn,nextHumanTurnPresented,nextTurnCast,nextCreaturePresented,repeatCycle,repeatedCombatPresented,repeatedTurnPresented;private long repeatLifeBefore=-1;private int repeatStartSnapshots;private int turnReadySnapshots,snapshotReadOnly;private long turnNumber=-1,loopStartTurn=-1,loopSubmittedRevision=-1;private int activeHuman;private string turnPhase;private long blockerDamage=-1,blockerDamageBefore=-1,blockerDamageAfter=-1,blockedLifeBefore=-1,blockedLifeAfter=-1;
        private bool OpeningLayout=>!land && !creature && !combatFinish && !selectAttacker;
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
        private Button InputButton(string name)=>selectAttacker?panel.Root.Query<Button>().ToList().Find(button=>button.text=="Select attacker"):combatFinish?panel.Root.Query<Button>().ToList().Find(button=>button.text=="Finish attacks"):priority?panel.Root.Query<Button>().ToList().Find(button=>button.text=="Pass priority"):panel.Root.Q<Button>(name);
        private void LimitActions()
        {
            if(selectAttacker){foreach(var button in panel.Root.Query<Button>().ToList())button.style.display=button.text=="Select attacker"?DisplayStyle.Flex:DisplayStyle.None;return;}
            if(!land)return;
            foreach(var button in panel.Root.Query<Button>().ToList())if(button.name.StartsWith("decision-action-"))button.style.display=(priority?button.text=="Pass priority":button.text!="Pass priority")?DisplayStyle.Flex:DisplayStyle.None;
        }
        private bool BlockerNamesPresented(){string summary=Volatile.Read(ref blockerSummary);return postDeclaredPriorityPresented && !string.IsNullOrEmpty(summary) && !summary.Contains("Unknown blocker");}
        private bool Report(string name,bool cleared=false)
        {
            try{var value=new JObject{["probe_version"]=1,["live_opening"]=true,["snapshot_count"]=Volatile.Read(ref snapshots),["ack_count"]=Volatile.Read(ref acks),["confirmed_receipt_count"]=Volatile.Read(ref confirmedReceipts),["uncertain_receipt_count"]=Volatile.Read(ref uncertainReceipts),["post_resolution_priority_presented"]=postResolutionPass && battlefieldPresented,["phase_transition_presented"]=phasePresented,["combat_cleanup_presented"]=combatCleanupPresented,["combat_group_count"]=Volatile.Read(ref combatGroupCount),["postcombat_defender_life"]=Interlocked.Read(ref defenderLife),["combat_damage_presented"]=combatDamagePresented,["defender_life_before"]=damageLifeBefore,["defender_life_after"]=damageLifeAfter,["post_declared_priority_presented"]=postDeclaredPriorityPresented,["repeated_combat_presented"]=repeatedCombatPresented,["repeated_turn_presented"]=repeatedTurnPresented,["repeat_defender_life_before"]=repeatLifeBefore,["repeat_defender_life_after"]=Interlocked.Read(ref defenderLife),["next_turn_creature_presented"]=nextCreaturePresented,["next_human_turn_presented"]=nextHumanTurnPresented,["turn_number"]=Interlocked.Read(ref turnNumber),["turn_loop_start"]=loopStartTurn,["blocked_damage_presented"]=blockedDamagePresented,["blocker_damage_before"]=blockerDamageBefore,["blocker_damage_after"]=blockerDamageAfter,["blocked_defender_life_before"]=blockedLifeBefore,["blocked_defender_life_after"]=blockedLifeAfter,["native_blocker_count_presented"]=Volatile.Read(ref combatBlockerCount),["native_blocker_names_presented"]=BlockerNamesPresented(),["native_blockers_presented"]=Volatile.Read(ref combatBlockerCount)>0,["declared_attack_presented"]=declaredAttackPresented,["attack_assignment_presented"]=attackAssignmentPresented,["attacker_choice_presented"]=selectAttacker && InputButton("")!=null,["attack_finish_presented"]=combatFinish && InputButton("")!=null,["post_combat_priority_presented"]=combatResultPresented,["combat_priority_action_presented"]=combatResultPresented && combatPriority,["combat_priority_result_presented"]=combatPriorityResultPresented,["followup_priority_presented"]=followupPresented,["battlefield_observation_presented"]=battlefieldPresented,["viewer_cleared"]=cleared,["arena_button_glows"]=buttonGlow?.Count??0,["arena_button_skins"]=buttonSkins,["mulligan_controls"]=mulliganControls,["arena_backdrop_resource"]=backdrop?ArenaOpeningBackdrop.ResourceName:null,["arena_backdrop"]=backdrop,["artwork_count"]=surface?.PresentedArtworkCount??0};
                string path=Path.Combine(output,name+".json");File.WriteAllText(path+".tmp",value.ToString());File.Move(path+".tmp",path);return true;}catch{return false;}
        }
        private void Fail(){host?.Dispose();Report("failed");Application.Quit(1);}
        private IEnumerator Start()
        {
            output=ArtworkFixtureScene.Argument("-manaforgeLiveOpening");capture=ArtworkFixtureScene.Argument("-manaforgeLiveCapture")=="1";
            priority=ArtworkFixtureScene.Argument("-manaforgeLivePriority")=="1";
            creature=ArtworkFixtureScene.Argument("-manaforgeLiveCreature")=="1";
            repeatCycle=ArtworkFixtureScene.Argument("-manaforgeLiveRepeatCycle")=="1";
            nextTurnCast=ArtworkFixtureScene.Argument("-manaforgeLiveNextTurnCast")=="1";
            loopTurn=ArtworkFixtureScene.Argument("-manaforgeLiveLoopTurn")=="1";
            blockedDamage=ArtworkFixtureScene.Argument("-manaforgeLiveBlockedDamage")=="1";
            blockedCombat=ArtworkFixtureScene.Argument("-manaforgeLiveBlockedCombat")=="1";
            completeCombat=ArtworkFixtureScene.Argument("-manaforgeLiveCompleteCombat")=="1";
            combatDamage=ArtworkFixtureScene.Argument("-manaforgeLiveCombatDamage")=="1";
            declaredPriority=ArtworkFixtureScene.Argument("-manaforgeLiveDeclaredPriority")=="1";
            finishSelectedAttack=ArtworkFixtureScene.Argument("-manaforgeLiveFinishSelectedAttack")=="1";
            selectAttacker=ArtworkFixtureScene.Argument("-manaforgeLiveSelectAttacker")=="1";
            combatFinish=ArtworkFixtureScene.Argument("-manaforgeLiveFinishAttacks")=="1";
            if(repeatCycle && !nextTurnCast){Application.Quit(1);yield break;}
            if(nextTurnCast && !loopTurn){Application.Quit(1);yield break;}
            if(loopTurn && !completeCombat){Application.Quit(1);yield break;}
            if(blockedDamage && !blockedCombat){Application.Quit(1);yield break;}
            if(blockedCombat && (!declaredPriority || combatDamage)){Application.Quit(1);yield break;}
            if(completeCombat && !combatDamage){Application.Quit(1);yield break;}
            if(combatDamage && !declaredPriority){Application.Quit(1);yield break;}
            if(declaredPriority && !finishSelectedAttack){Application.Quit(1);yield break;}
            if(finishSelectedAttack && !selectAttacker){Application.Quit(1);yield break;}
            if(selectAttacker && (combatFinish || creature || priority)){Application.Quit(1);yield break;}
            if(combatFinish && (creature || priority)){Application.Quit(1);yield break;}
            combatPriority=ArtworkFixtureScene.Argument("-manaforgeLiveCombatPriority")=="1";
            if(combatPriority && !combatFinish){Application.Quit(1);yield break;}
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
                if(selectAttacker)title.text="LIVE XMAGE - SELECT ATTACKER";
                if(combatFinish)title.text="LIVE XMAGE - FINISH ATTACKS";
                status=new Label("Connecting to the owned Java gateway…");status.style.color=Color.white;root.Add(status);
                note=new Label(blockedDamage?"Public Memnite versus Ornithopter decks. Observe native marked damage on the blocker; no human blocker choice.":blockedCombat?"Public Memnite versus Ornithopter decks. Observe native AI blockers; no human blocker choice or blocked damage.":combatDamage?"Public Memnite/Forest decks. Explicit unblocked 1/1 combat fixture; native life change observation only.":selectAttacker?"Public Memnite/Forest decks. Choose one attacker. No blocking or damage.":combatPriority?"Public Memnite/Forest decks. Finish attacks, then one explicit priority pass. Setup used diagnostic policy; no full match.":combatFinish?"Public Memnite/Forest decks. Setup used diagnostic policy before connection. Explicit Finish attacks only; no attackers chosen, no full match.":postResolutionPass?"Public Memnite/Forest decks. Choose the ability, then two explicit priority passes. Observe the next phase; no full match.":continuePriority?"Public Memnite/Forest decks. Choose the casting ability, then one priority pass. Stack contents unavailable; no full match.":creature?"Public Memnite/Forest decks. Diagnostic card click completed. Choose the casting ability; Java checks the stack entry.":priority?"Public Forest decks. Diagnostic setup completed. One explicit priority pass; no full match.":land?"Public Forest decks. Diagnostic pregame/keep already completed. One land action only; no full match.":artwork?"Public Forest/Ornithopter decks. Verified offline artwork. Current rules / tap state unavailable; one opening decision only.":"Public Forest/Memnite decks. Opening decision only; artwork cache and later gameplay are not connected.");note.style.color=requestedBackdrop?new Color(.9f,.9f,.9f):Color.gray;root.Add(note);
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
                var token=cancellation.Token;consuming=Task.Run(()=>{while(!token.IsCancellationRequested && !host.Completion.IsCompleted){if(host.TryTake(out var update))using(update){if(update.Receive.Type=="snapshot"){Interlocked.Exchange(ref snapshotReadOnly,update.Decision!=null && update.Decision.Decision==null && update.Decision.Actions.Count==0?1:0);Interlocked.Exchange(ref turnNumber,update.Decision?.Turn??-1);Interlocked.Exchange(ref turnPhase,update.Decision?.Phase);Interlocked.Exchange(ref activeHuman,update.Decision?.ActivePlayerId==update.Decision?.Context.ViewerId?1:0);var combat=update.Decision?.Combat;Interlocked.Exchange(ref blockerSummary,combat?.Count==1 && combat[0].BlockerNames.Count>0?string.Join(", ",combat[0].BlockerNames):null);Interlocked.Exchange(ref attackAssignmentSummary,combat?.Count==1 && combat[0].AttackerNames.Count==1?combat[0].AttackerNames[0]+" attacks "+combat[0].DefenderName+(combat[0].BlockerCount>0?"; native blockers: "+string.Join(", ",combat[0].BlockerNames):"")+". Declaration remains open.":null);Interlocked.Exchange(ref blockerDamage,combat?.Count==1 && combat[0].BlockerDamage.Count==1?combat[0].BlockerDamage[0]??-1:-1);Interlocked.Exchange(ref combatBlockerCount,combat?.Count==1?combat[0].BlockerCount:-1);Interlocked.Exchange(ref combatGroupCount,combat?.Count??-1);if(combat?.Count==1)Interlocked.Exchange(ref combatDefenderId,combat[0].DefenderId);string defender=Volatile.Read(ref combatDefenderId);long? life=null;if(defender!=null)update.Decision?.PlayerLifeTotals.TryGetValue(defender,out life);Interlocked.Exchange(ref defenderLife,life??-1);Interlocked.Exchange(ref snapshotRevision,update.Decision?.Context.Revision??-1);Interlocked.Increment(ref snapshots);}if(update.Receive.Type=="ack"){Interlocked.Increment(ref acks);if(update.Receive.Receipt?.State==CommandState.Confirmed)Interlocked.Increment(ref confirmedReceipts);if(update.Receive.Receipt?.State==CommandState.Uncertain)Interlocked.Increment(ref uncertainReceipts);}}else Thread.Sleep(10);}});
            }catch{Fail();yield break;}
            double deadline=Time.realtimeSinceStartupAsDouble+20;
            string control=land?"decision-action-0":"decision-option-0";
            while(!host.Completion.IsCompleted && ((OpeningLayout && surface.CardsRoot.childCount!=7) || InputButton(control)==null || artwork && (surface.ExpectedArtworkCount==0 || surface.PresentedArtworkCount<surface.ExpectedArtworkCount))){
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
            status.text=selectAttacker?"Connected to real XMage. Choose Select attacker; this probe ends after submission.":combatFinish?"Connected to real XMage. Select the offered Finish attacks response.":creature?"Connected to real XMage. Select the offered casting ability.":priority?"Connected to real XMage. Select Pass priority to yield this decision.":land?"Connected to real XMage. Select an offered Play land action.":"Connected to real XMage. Inspect your opening hand, then choose whether to mulligan.";
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
                if(postResolutionPass && !phasePresented && Volatile.Read(ref snapshots)==4 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    if(host.PresentedDecision!=null || panel.Root.Query<Button>().ToList().Count!=0){Fail();yield break;}
                    phasePresented=true;inspect.Clear();
                    foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text="The exact pass is confirmed; XMage advanced its phase or step. Read-only state.";
                    if(capture)yield return Capture("phase.png");if(!Report("phase-ready")){Application.Quit(1);yield break;}
                }
                if(selectAttacker && !attackAssignmentPresented && Volatile.Read(ref snapshots)==2 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    string summary=Volatile.Read(ref attackAssignmentSummary);
                    var controls=panel.Root.Query<Button>().ToList();var finish=controls.Find(button=>button.text=="Finish attacks");
                    if(summary==null || (finishSelectedAttack?(controls.Count!=1 || finish==null || !finish.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || controls.Count!=0))){Fail();yield break;}
                    attackAssignmentPresented=true;inspect.Clear();
                    foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text=finishSelectedAttack?summary+" Choose Finish attacks.":summary;
                    if(capture)yield return Capture("attack-assignment.png");if(!Report("attack-assignment-ready")){Application.Quit(1);yield break;}
                    if(finishSelectedAttack && ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=finish;finish.SendEvent(input);}
                }
                if(finishSelectedAttack && !declaredAttackPresented && Volatile.Read(ref snapshots)==3 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    var controls=panel.Root.Query<Button>().ToList();var pass=controls.Find(button=>button.text=="Pass priority");
                    if(Volatile.Read(ref attackAssignmentSummary)==null || (declaredPriority?(controls.Count!=1 || pass==null || !pass.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || controls.Count!=0))){Fail();yield break;}
                    declaredAttackPresented=true;inspect.Clear();foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text=Volatile.Read(ref attackAssignmentSummary).Replace("Declaration remains open.","Declaration finished; native priority observed.");
                    if(capture)yield return Capture("declared-attack.png");if(!Report("declared-attack-ready")){Application.Quit(1);yield break;}
                    if(declaredPriority && ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=pass;pass.SendEvent(input);}
                }
                if(declaredPriority && !postDeclaredPriorityPresented && Volatile.Read(ref snapshots)==4 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    var controls=panel.Root.Query<Button>().ToList();var pass=controls.Find(button=>button.text=="Pass priority");
                    if(Volatile.Read(ref attackAssignmentSummary)==null || ((combatDamage || blockedDamage)?(controls.Count!=1 || pass==null || !pass.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || controls.Count!=0))){Fail();yield break;}
                    if(blockedDamage){blockerDamageBefore=Interlocked.Read(ref blockerDamage);blockedLifeBefore=Interlocked.Read(ref defenderLife);if(blockerDamageBefore!=0 || blockedLifeBefore<0){Fail();yield break;}}
                    if(combatDamage){damageLifeBefore=Interlocked.Read(ref defenderLife);if(damageLifeBefore<=1){Fail();yield break;}}
                    if(blockedCombat && (Volatile.Read(ref combatBlockerCount)<=0 || string.IsNullOrEmpty(Volatile.Read(ref blockerSummary)) || Volatile.Read(ref blockerSummary).Contains("Unknown blocker"))){Fail();yield break;}
                    postDeclaredPriorityPresented=true;inspect.Clear();foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text=Volatile.Read(ref attackAssignmentSummary).Replace("Declaration remains open.","Priority pass confirmed; next native combat state observed.");
                    if(capture)yield return Capture("post-declared-priority.png");if(!Report("post-declared-priority-ready")){Application.Quit(1);yield break;}
                    if((combatDamage || blockedDamage) && ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=pass;pass.SendEvent(input);}
                }
                if(blockedDamage && !blockedDamagePresented && Volatile.Read(ref snapshots)==5 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    blockerDamageAfter=Interlocked.Read(ref blockerDamage);blockedLifeAfter=Interlocked.Read(ref defenderLife);
                    if(host.PresentedDecision!=null || panel.Root.Query<Button>().ToList().Count!=0 || Volatile.Read(ref combatBlockerCount)!=1 || !BlockerNamesPresented() || blockerDamageAfter!=1 || blockedLifeAfter!=blockedLifeBefore){Fail();yield break;}
                    blockedDamagePresented=true;inspect.Clear();foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text=Volatile.Read(ref blockerSummary)+" native marked damage: "+blockerDamageBefore+" -> "+blockerDamageAfter+". Defender life remains "+blockedLifeAfter+".";
                    if(capture)yield return Capture("blocked-damage.png");if(!Report("blocked-damage-ready")){Application.Quit(1);yield break;}
                }
                if(combatDamage && !combatDamagePresented && Volatile.Read(ref snapshots)==5 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    damageLifeAfter=Interlocked.Read(ref defenderLife);
                    var controls=panel.Root.Query<Button>().ToList();var pass=controls.Find(button=>button.text=="Pass priority");
                    if(Volatile.Read(ref attackAssignmentSummary)==null || damageLifeAfter!=damageLifeBefore-1 || (completeCombat?(controls.Count!=1 || pass==null || !pass.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || controls.Count!=0))){Fail();yield break;}
                    combatDamagePresented=true;inspect.Clear();foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text="Confirmed native combat-damage observation. Defender life: "+damageLifeBefore+" -> "+damageLifeAfter+".";
                    if(capture)yield return Capture("combat-damage.png");if(!Report("combat-damage-ready")){Application.Quit(1);yield break;}
                    if(completeCombat && ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=pass;pass.SendEvent(input);}
                }
                if(completeCombat && !combatCleanupPresented && Volatile.Read(ref snapshots)==6 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    var controls=panel.Root.Query<Button>().ToList();var pass=controls.Find(button=>button.text=="Pass priority");
                    if((loopTurn?(controls.Count!=1 || pass==null || !pass.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || controls.Count!=0)) || Volatile.Read(ref combatGroupCount)!=0 || Interlocked.Read(ref defenderLife)!=damageLifeAfter){Fail();yield break;}
                    if(loopTurn)loopStartTurn=Interlocked.Read(ref turnNumber);
                    combatCleanupPresented=true;inspect.Clear();foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text="Native post-combat main observed. Combat cleared; defender life remains "+damageLifeAfter+".";
                    if(capture)yield return Capture("combat-cleanup.png");if(!Report("combat-cleanup-ready")){Application.Quit(1);yield break;}
                }
                if(loopTurn && combatCleanupPresented && (!nextHumanTurnPresented || nextTurnCast && !nextCreaturePresented || repeatCycle && !repeatedTurnPresented) && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    long currentRevision=Interlocked.Read(ref snapshotRevision);var controls=panel.Root.Query<Button>().ToList();var cast=controls.Find(value=>value.text=="Cast spell");
                    if(!nextHumanTurnPresented && Volatile.Read(ref snapshots)>6 && (nextTurnCast?(cast!=null && host.PresentedDecision?.CanSubmit==true):(host.PresentedDecision==null && controls.Count==0)) && Volatile.Read(ref activeHuman)==1 && Interlocked.Read(ref turnNumber)==loopStartTurn+2 && Volatile.Read(ref turnPhase)=="PRECOMBAT_MAIN"){
                        nextHumanTurnPresented=true;turnReadySnapshots=Volatile.Read(ref snapshots);inspect.Clear();status.text="Next human main phase reached. Native draw, untap and cleanup observed.";if(!Report("next-human-turn-ready")){Application.Quit(1);yield break;}
                    }
                    if(nextTurnCast && nextHumanTurnPresented && Volatile.Read(ref snapshots)==turnReadySnapshots+3 && (repeatCycle?(host.PresentedDecision?.CanSubmit==true && controls.Count==1 && controls[0].text=="Pass priority"):(Volatile.Read(ref snapshotReadOnly)==1 && host.PresentedDecision==null && controls.Count==0))){
                        nextCreaturePresented=true;repeatLifeBefore=Interlocked.Read(ref defenderLife);repeatStartSnapshots=Volatile.Read(ref snapshots);inspect.Clear();foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);status.text="Next-turn creature cast and resolved on the same session.";if(!Report("next-turn-creature-ready")){Application.Quit(1);yield break;}
                    }
                    if(repeatCycle && nextCreaturePresented && !repeatedCombatPresented && Volatile.Read(ref snapshots)>repeatStartSnapshots && host.PresentedDecision?.CanSubmit==true && controls.Count==1 && controls[0].text=="Pass priority" && Volatile.Read(ref combatGroupCount)==0 && Volatile.Read(ref turnPhase)=="POSTCOMBAT_MAIN" && Interlocked.Read(ref turnNumber)==loopStartTurn+2){
                        if(Interlocked.Read(ref defenderLife)!=repeatLifeBefore-1){Fail();yield break;}repeatedCombatPresented=true;inspect.Clear();status.text="Second combat completed on the same session. Defender life: "+repeatLifeBefore+" -> "+Interlocked.Read(ref defenderLife)+".";if(!Report("repeated-combat-ready")){Application.Quit(1);yield break;}
                    }
                    if(repeatCycle && repeatedCombatPresented && !repeatedTurnPresented && Volatile.Read(ref snapshotReadOnly)==1 && host.PresentedDecision==null && controls.Count==0 && Volatile.Read(ref combatGroupCount)==0 && Volatile.Read(ref activeHuman)==1 && Volatile.Read(ref turnPhase)=="PRECOMBAT_MAIN" && Interlocked.Read(ref turnNumber)==loopStartTurn+4){
                        if(Interlocked.Read(ref defenderLife)!=repeatLifeBefore-1){Fail();yield break;}repeatedTurnPresented=true;inspect.Clear();status.text="Another AI turn completed; human draw and untap confirmed.";if(!Report("repeated-turn-ready")){Application.Quit(1);yield break;}
                    }else if((!nextCreaturePresented || repeatCycle && !repeatedTurnPresented) && host.PresentedDecision?.CanSubmit==true && currentRevision!=loopSubmittedRevision){
                        var button=cast??controls.Find(value=>value.text=="Pass priority" || value.text.StartsWith("Discard ") || repeatCycle && (value.text=="Select attacker" || value.text=="Finish attacks"));if(button==null && nextTurnCast && nextHumanTurnPresented && controls.Count==1)button=controls[0];if(button==null){Fail();yield break;}
                        status.text="Gameplay continuation: "+Volatile.Read(ref turnPhase)+". Choose the offered response.";foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                        if(ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1"){loopSubmittedRevision=currentRevision;using(var input=NavigationSubmitEvent.GetPooled()){input.target=button;button.SendEvent(input);}}
                    }
                }
                if(combatFinish && !combatResultPresented && Volatile.Read(ref snapshots)==2 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    var controls=panel.Root.Query<Button>().ToList();var pass=controls.Find(button=>button.text=="Pass priority");
                    if(combatPriority?(controls.Count!=1 || pass==null || !pass.enabledInHierarchy || host.PresentedDecision?.CanSubmit!=true):(host.PresentedDecision!=null || controls.Count!=0)){Fail();yield break;}
                    combatResultPresented=true;inspect.Clear();
                    foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text=combatPriority?"Finish attacks confirmed. Choose the next native Pass priority.":"Finish attacks confirmed. The next native priority state is shown read-only.";
                    if(capture)yield return Capture("combat-result.png");if(!Report("combat-result-ready")){Application.Quit(1);yield break;}
                    if(combatPriority && ArtworkFixtureScene.Argument("-manaforgeLiveScript")=="1")using(var input=NavigationSubmitEvent.GetPooled()){input.target=pass;pass.SendEvent(input);}
                }
                if(combatPriority && !combatPriorityResultPresented && Volatile.Read(ref snapshots)==3 && host.HasPresentedRevision(Interlocked.Read(ref snapshotRevision))){
                    if(host.PresentedDecision!=null || panel.Root.Query<Button>().ToList().Count!=0){Fail();yield break;}
                    combatPriorityResultPresented=true;inspect.Clear();
                    foreach(var card in surface.CardsRoot.Children())if(card is CardView view)view.SetPresentation(CardPresentationMode.Compact,135);
                    status.text="The post-combat pass is confirmed. The next native state is shown read-only.";
                    if(capture)yield return Capture("combat-priority-result.png");if(!Report("combat-priority-ready")){Application.Quit(1);yield break;}
                }
                if(!choiceReported && Volatile.Read(ref acks)>=(completeCombat?10:(combatDamage || blockedDamage)?8:declaredPriority?6:finishSelectedAttack?4:combatPriority?4:postResolutionPass?6:continuePriority?4:2) && (!observeResolution || battlefieldPresented) && (!postResolutionPass || phasePresented) && (!repeatCycle || repeatedTurnPresented) && (!nextTurnCast || nextCreaturePresented) && (!loopTurn || nextHumanTurnPresented) && (!blockedDamage || blockedDamagePresented) && (!completeCombat || combatCleanupPresented) && (!combatDamage || combatDamagePresented) && (!declaredPriority || postDeclaredPriorityPresented) && (!finishSelectedAttack || declaredAttackPresented) && (!selectAttacker || attackAssignmentPresented) && (!combatFinish || combatResultPresented) && (!combatPriority || combatPriorityResultPresented)){
                    buttonGlow?.Dispose();buttonGlow=null;cardFocus?.Dispose();cardFocus=null;host.Cancel();host.Tick();panel.Tick();inspect.Clear();
                    status.text=repeatCycle?"Repeated cast and combat completed; inputs confirmed and viewer cleared.":nextTurnCast?"Next-turn cast, ability and resolution confirmed; viewer cleared.":loopTurn?"Gameplay cycle returned to the human main phase; all turn inputs confirmed and viewer cleared.":blockedDamage?"Four combat inputs confirmed. Native blocker damage displayed; viewer cleared.":completeCombat?"All five combat inputs confirmed. Post-combat main and cleared combat observed; viewer cleared.":combatDamage?"All four combat inputs confirmed. Native life change displayed; viewer cleared.":declaredPriority?"All three combat inputs confirmed. Next native state observed; viewer cleared.":finishSelectedAttack?"Attacker selection and Finish attacks confirmed. Native priority observed; viewer cleared.":selectAttacker?"Attacker choice confirmed; native assignment displayed. Declaration remains open. Viewer cleared.":combatPriority?"Finish attacks and next priority pass confirmed. Next native state observed; viewer cleared.":combatFinish?"Finish attacks confirmed; native empty combat advanced. Viewer cleared.":postResolutionPass?"All three choices confirmed; next native phase observed. Viewer cleared; this test ends here.":observeResolution?"Casting ability and exact priority pass confirmed; battlefield observed. Viewer cleared; this test ends here.":continuePriority?"Casting ability confirmed; next priority pass submitted. Pass outcome uncertain. Viewer cleared; this test ends here.":creature?"Casting ability submitted; native Memnite stack entry observed. Viewer cleared; this test ends here.":priority?"Priority pass submitted to XMage; engine advanced. Viewer cleared; this test ends here.":"Choice submitted to XMage. Next-state support ends here; viewer cleared. No confirmed result is claimed.";
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
