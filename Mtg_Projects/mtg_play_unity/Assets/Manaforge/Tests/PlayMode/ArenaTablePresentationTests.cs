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
                    Assert.That(localSeat.worldBound.center.x,Is.EqualTo(size.x*.5f).Within(2));Assert.That(opposingSeat.worldBound.center.x,Is.EqualTo(size.x*.5f).Within(2));
                    Assert.That(views["table-1"].worldBound.Overlaps(localSeat.worldBound),Is.False,"Tapped lands must leave the life medallion visible");

                    foreach(var view in views.Values){Assert.That(view.resolvedStyle.left,Is.GreaterThanOrEqualTo(0));Assert.That(view.resolvedStyle.left+view.resolvedStyle.width,Is.LessThanOrEqualTo(size.x));}
                }
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
                Assert.That(table.Surface.ClearViewer(ticket),Is.True);int visited=0;table.Surface.VisitPresented((c,v)=>visited++);Assert.That(visited,Is.Zero);Assert.That(table.Surface.CardsRoot.childCount,Is.Zero);
            }finally{table.Dispose();Object.Destroy(gameObject);Object.Destroy(settings);}
            yield return null;
        }
    }
}
