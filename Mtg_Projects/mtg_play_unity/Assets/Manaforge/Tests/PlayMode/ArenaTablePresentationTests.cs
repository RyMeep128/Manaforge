using System.Collections;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
namespace Manaforge.Play.Tests
{
    public sealed class ArenaTablePresentationTests
    {
        [UnityTest] public IEnumerator AuraSitsWithItsHostAndCountOpensTheAttachmentBrowser()
        {
            var node=new GameObject("Attachment presentation");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;document.rootVisualElement.style.width=1280;document.rootVisualElement.style.height=720;var table=new ArenaGameplayPresentation(document.rootVisualElement);
            try{
                var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));var message=(JObject)corpus["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();snapshot["turn"]=2;
                var host=(JObject)snapshot["objects"][0].DeepClone();host["object_id"]="enchanted-host";host["zone"]="battlefield";host["hidden"]=false;host["face_down"]=false;host["tapped"]=false;host["characteristics"]["name"]="Enchanted creature";host["characteristics"]["type_line"]="Creature";host["attachments"]=new JArray("public-aura");host["attached_to"]=null;
                var aura=(JObject)host.DeepClone();aura["object_id"]="public-aura";aura["characteristics"]["name"]="Public Aura";aura["characteristics"]["type_line"]="Enchantment — Aura";aura["attachments"]=new JArray();aura["attached_to"]="enchanted-host";snapshot["objects"]=new JArray(host,aura);
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=table.Surface.BeginViewer(session,viewer);table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));yield return null;table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));
                CardView parent=null,attached=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="enchanted-host")parent=view;if(card.ObjectId=="public-aura")attached=view;});Assert.That(parent,Is.Not.Null);Assert.That(attached,Is.Not.Null);Assert.That(attached.style.left.value.value,Is.GreaterThan(parent.style.left.value.value));Assert.That(attached.style.top.value.value,Is.GreaterThan(parent.style.top.value.value));
                var badge=document.rootVisualElement.Q<Button>("attachment-count-enchanted-host");Assert.That(badge,Is.Not.Null);using(var click=NavigationSubmitEvent.GetPooled()){click.target=badge;badge.SendEvent(click);}Assert.That(document.rootVisualElement.Q<Label>("public-zone-title").text,Does.Contain("Attachments"));Assert.That(attached.Mode,Is.EqualTo(CardPresentationMode.Full));
                table.ClosePublicZone();snapshot["revision"]=(long)snapshot["revision"]+1;host["attachments"]=new JArray();aura["attached_to"]=null;table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));Assert.That(document.rootVisualElement.Q<Button>("attachment-count-enchanted-host"),Is.Null);
            }finally{table.Dispose();Object.Destroy(node);Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator StackAutomaticallyExpandsAndClearsItsToolbar()
        {
            var node=new GameObject("Stack focus presentation");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;document.rootVisualElement.style.width=1280;document.rootVisualElement.style.height=720;
            var table=new ArenaGameplayPresentation(document.rootVisualElement);
            try{
                var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));var message=(JObject)corpus["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();var card=snapshot["objects"][0];card["zone"]="stack";card["hidden"]=false;card["face_down"]=false;card["characteristics"]["type_line"]="Ability";
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=table.Surface.BeginViewer(session,viewer);
                table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));yield return null;
                var toggle=document.rootVisualElement.Q<Button>("stack-focus-toggle");Assert.That(toggle.text,Is.EqualTo("Minimize"));Assert.That(document.rootVisualElement.Q<Button>("stack-resolve-all").style.display.value,Is.EqualTo(DisplayStyle.Flex));
                using(var click=ClickEvent.GetPooled()){click.target=toggle;toggle.SendEvent(click);}Assert.That(toggle.text,Is.EqualTo("View"));
                snapshot["revision"]=(long)snapshot["revision"]+1;snapshot["objects"]=new JArray();table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));
                Assert.That(document.rootVisualElement.Q<VisualElement>("stack-toolbar").style.display.value,Is.EqualTo(DisplayStyle.None));
            }finally{table.Dispose();Object.Destroy(node);Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator HoverReturnsToKeyboardPreviewAndRevocationClearsItWithoutACommand()
        {
            var node=new GameObject("Authenticated Arena focus test");var settings=ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            var table=new ArenaGameplayPresentation(document.rootVisualElement);ViewerSessionHost host=null;
            try{
                string fixtures=Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures");
                var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(fixtures,"receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();
                var snapshot=envelope["body"]["snapshot"];
                var card=JObject.Parse(File.ReadAllText(Path.Combine(fixtures,"wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0].DeepClone();
                card["object_id"]=snapshot["objects"][0]["object_id"];card["zone"]="hand";card["owner_id"]="one";card["controller_id"]="one";
                var grave=card.DeepClone();grave["object_id"]="grave-card";grave["zone"]="graveyard";
                snapshot["objects"]=new JArray(card,grave);
                using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());
                var owner=new System.Threading.Tasks.TaskCompletionSource<bool>(System.Threading.Tasks.TaskCreationOptions.RunContinuationsAsynchronously);
                host=new ViewerSessionHost(table.Surface,peer.Bootstrap(),owner.Task,true);table.Bind(host);
                float deadline=Time.realtimeSinceStartup+10;
                while(host.PresentedDecision==null && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                Assert.That(host.PresentedDecision,Is.Not.Null);table.Decisions.Tick();table.Present(host.PresentedDecision.Frame);yield return null;
                CardView view=null;table.Surface.VisitPresented((projected,presented)=>{if(projected.Zone=="hand")view=presented;});Assert.That(view,Is.Not.Null);
                view.Focus();yield return null;
                using(var enter=PointerEnterEvent.GetPooled()){enter.target=view;view.SendEvent(enter);}
                using(var leave=PointerLeaveEvent.GetPooled()){leave.target=view;view.SendEvent(leave);}
                Assert.That(table.Surface.InspectionView.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));
                Assert.That(table.Surface.InspectionView.Q<Label>("name").text,Is.Not.Empty);
                Assert.That(peer.PendingCommandBytes,Is.Zero,"Focus and hover are presentation-only");
                Assert.That(table.BrowsePublicZone("graveyard","one"),Is.True);yield return null;
                table.Present(host.PresentedDecision.Frame);yield return null;
                Assert.That(document.rootVisualElement.Q<Label>("board-input-hint"),Is.Null,"The table must not mount instructional hints");
                owner.TrySetResult(true);deadline=Time.realtimeSinceStartup+10;
                while(!host.Completion.IsCompleted && Time.realtimeSinceStartup<deadline)yield return null;
                Assert.That(host.Completion.IsCompleted,Is.True);host.Tick();yield return null;
                Assert.That(table.Surface.InspectionView.Q<Label>("name").text,Is.Empty);
                Assert.That(table.Surface.CardsRoot.childCount,Is.Zero);
            }finally{host?.Dispose();table.Dispose();Object.Destroy(node);Object.Destroy(settings);}
            yield return null;
        }
        [UnityTest] public IEnumerator AuthenticatedZonesRemainDistinctAtDesktopSizesAndClearOnHandoff()
        {
            var gameObject=new GameObject("Arena table test");var settings=ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=gameObject.AddComponent<UIDocument>();doc.panelSettings=settings;
            var table=new ArenaGameplayPresentation(doc.rootVisualElement);
            try {
                var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
                var snapshot=envelope["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();
                string viewer=(string)snapshot["viewer_id"],session=(string)snapshot["session_id"],other=(string)snapshot["players"][1]["player_id"];
                var original=snapshot["objects"][0].DeepClone();var cards=new JArray();
                for(int i=0;i<4;i++){
                    var card=original.DeepClone();card["object_id"]="table-"+i;card["owner_id"]=i==3?other:viewer;card["controller_id"]=i==3?other:viewer;
                    card["zone"]=i==0?"hand":"battlefield";card["characteristics"]["name"]="Same visible name";card["characteristics"]["type_line"]=i==1?"Basic Land":"Artifact Creature";card["tapped"]=i==1;
                    cards.Add(card);
                }
                snapshot["objects"]=cards;
                var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;
                var cardFrame=ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true);
                Assert.That(table.Surface.TryPresent(ticket,cardFrame),Is.True);
                var frame=ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true);
                var views=new Dictionary<string,CardView>();table.Surface.VisitPresented((c,v)=>views.Add(c.ObjectId,v));
                foreach(var size in new[]{new Vector2(1280,720),new Vector2(1366,768),new Vector2(1920,1080),new Vector2(2560,1440)}){
                    doc.rootVisualElement.style.width=size.x;doc.rootVisualElement.style.height=size.y;yield return null;table.Present(frame);yield return null;
                    Assert.That(views["table-3"].resolvedStyle.top,Is.LessThan(views["table-2"].resolvedStyle.top));
                    Assert.That(views["table-2"].resolvedStyle.top,Is.LessThan(views["table-1"].resolvedStyle.top));
                    Assert.That(views["table-1"].style.rotate.value.angle.value,Is.EqualTo(90));Assert.That(views["table-1"].Q<Label>("status").resolvedStyle.display,Is.EqualTo(DisplayStyle.None));
                    var localSeat=doc.rootVisualElement.Q<Label>("local-seat");var opposingSeat=doc.rootVisualElement.Q<Label>("opponent-seat");
                    Assert.That(doc.rootVisualElement.Query<PlayerPanel>().ToList().Count,Is.EqualTo(2));
                    Assert.That(localSeat.worldBound.xMax,Is.LessThan(260));Assert.That(opposingSeat.worldBound.xMax,Is.LessThan(260));
                    Assert.That(localSeat.worldBound.Overlaps(opposingSeat.worldBound),Is.False);
                    Assert.That(views["table-1"].worldBound.Overlaps(localSeat.worldBound),Is.False,"Tapped lands must leave the life medallion visible");

                    foreach(var view in views.Values){Assert.That(view.resolvedStyle.left,Is.GreaterThanOrEqualTo(0));Assert.That(view.resolvedStyle.left+view.resolvedStyle.width,Is.LessThanOrEqualTo(size.x));}
                }
                doc.rootVisualElement.style.width=1280;doc.rootVisualElement.style.height=720;yield return null;
                // Pointer focus temporarily overrides keyboard focus and returns to it on leave.
                views["table-2"].Focus();yield return null;
                using(var enter=PointerEnterEvent.GetPooled()){enter.target=views["table-3"];views["table-3"].SendEvent(enter);}
                Assert.That(views["table-3"].style.scale.value.value.x,Is.EqualTo(1.12f));
                Assert.That(views["table-2"].style.scale.value.value.x,Is.EqualTo(1));
                using(var leave=PointerLeaveEvent.GetPooled()){leave.target=views["table-3"];views["table-3"].SendEvent(leave);}
                Assert.That(views["table-2"].style.scale.value.value.x,Is.EqualTo(1.12f));
                Assert.That(views["table-3"].style.scale.value.value.x,Is.EqualTo(1));
                for(int i=4;i<20;i++){var extra=cards[2].DeepClone();extra["object_id"]="crowd-"+i;cards.Add(extra);}
                snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                var next=doc.rootVisualElement.Q<Button>("local-permanents-next");Assert.That(next,Is.Not.Null);Assert.That(next.enabledInHierarchy,Is.True);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=next;next.SendEvent(submit);}yield return null;
                Assert.That(views["table-2"].resolvedStyle.display,Is.EqualTo(DisplayStyle.None));
                for(int i=0;i<2;i++){var commander=original.DeepClone();commander["object_id"]="command-"+i;commander["zone"]="command";commander["owner_id"]=i==0?viewer:other;commander["controller_id"]=null;cards.Add(commander);}
                snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.Zone=="command")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex),"Both public command zones remain available for inspection and native offers");});
                // With a normal (non-opening) hand, rotated cards leave the action rail clear.
                snapshot["turn"]=2;
                // Large hands stay selectable through keyboard paging; public-zone browsing
                // preserves authenticated ownership even when every card has the same name.
                for(int i=0;i<30;i++){var extra=cards[0].DeepClone();extra["object_id"]="hand-"+i;cards.Add(extra);}
                for(int i=0;i<2;i++){var extra=original.DeepClone();extra["object_id"]="grave-"+i;extra["zone"]="graveyard";extra["owner_id"]=i==0?viewer:other;extra["controller_id"]=null;cards.Add(extra);}
                snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.Zone=="hand" && view.resolvedStyle.display==DisplayStyle.Flex)Assert.That(view.worldBound.xMax,Is.LessThan(985),"Hand cards must leave the contextual action rail unobstructed");});
                var handNext=doc.rootVisualElement.Q<Button>("hand-next");Assert.That(handNext,Is.Not.Null);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=handNext;handNext.SendEvent(submit);}yield return null;
                Assert.That(views["table-0"].resolvedStyle.display,Is.EqualTo(DisplayStyle.None));
                doc.rootVisualElement.Q<GameplayDrawer>("zones-drawer").SetOpen(true);yield return null;
                var graveButton=doc.rootVisualElement.Q<Label>("opponent-graveyard");Assert.That(graveButton,Is.Not.Null);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=graveButton;graveButton.SendEvent(submit);}yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="grave-1")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));if(card.ObjectId=="grave-0")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None));});
                CardView graveView=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="grave-1")graveView=view;if(card.Zone=="battlefield" || card.Zone=="hand")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None));});
                Assert.That(graveView,Is.Not.Null);
                Assert.That(doc.rootVisualElement.Q<VisualElement>("board-navigation").childCount,Is.Zero,"Only the open zone's pagination may remain visible");
                var picked=doc.rootVisualElement.panel.Pick(graveView.worldBound.center);
                Assert.That(picked==graveView || picked!=null && graveView.Contains(picked),Is.True,"The drawer must not cover the displayed card's pointer target");
                Assert.That(table.BrowsePublicZone("hand",viewer),Is.False,"Private zones cannot be requested through public navigation");
                Assert.That(table.BrowsePublicZone("exile",other),Is.True,"Empty zones remain discoverable without fabricating cards");
                yield return null;
                Assert.That(doc.rootVisualElement.Q<Label>("zone-browser-summary").text,Does.Contain("No viewer-visible cards"));
                Assert.That(table.BrowsePublicZone("library","unknown-player"),Is.False);
                Assert.That(table.BrowsePublicZone("library",viewer),Is.True);yield return null;
                Assert.That(doc.rootVisualElement.Q<VisualElement>("zone-browser-back").resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));
                Assert.That(doc.rootVisualElement.Q<Label>("zone-browser-summary").text,Does.Contain("0 known"));
                table.Surface.VisitPresented((card,view)=>Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None),"Browsing a hidden library must not expose the hand or other zones"));
                var closeZone=doc.rootVisualElement.Q<Button>("close-public-zone");
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=closeZone;closeZone.SendEvent(submit);}yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.Zone=="graveyard")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None));});
                // A library search browser opens only for admitted engine-offered objects.
                var known=original.DeepClone();known["object_id"]="known-library-card";known["zone"]="library";known["owner_id"]=viewer;known["controller_id"]=JValue.CreateNull();cards.Add(known);
                var offered=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"]["body"]["snapshot"]["decision"].DeepClone();
                offered["family"]="selection";offered["is_priority"]=false;offered["can_finish"]=true;
                offered["options"]=new JArray(new JObject{["option_id"]="known-library-option",["label"]="Known card",["object_id"]="known-library-card",["player_id"]=JValue.CreateNull(),["selected"]=false});
                snapshot["decision"]=offered;snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                Assert.That(doc.rootVisualElement.Q<Label>("public-zone-title").text,Does.Contain("Library"));
                Assert.That(doc.rootVisualElement.Q<Label>("zone-browser-summary").text,Does.Contain("1 known"));
                Assert.That(doc.rootVisualElement.Q<VisualElement>("zone-browser-back").resolvedStyle.display,Is.EqualTo(DisplayStyle.None));
                table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="known-library-card")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));});
                Assert.That(table.Surface.ClearViewer(ticket),Is.True);int visited=0;table.Surface.VisitPresented((c,v)=>visited++);Assert.That(visited,Is.Zero);Assert.That(table.Surface.CardsRoot.childCount,Is.Zero);
            }finally{table.Dispose();Object.Destroy(gameObject);Object.Destroy(settings);}
            yield return null;
        }
    }
}
