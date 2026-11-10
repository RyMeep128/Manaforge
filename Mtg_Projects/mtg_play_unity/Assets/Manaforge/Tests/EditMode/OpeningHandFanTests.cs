using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine.UIElements;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningHandFanTests
    {
        [TestCase("Mulligan <font color='#ffff00'>down to 6 cards</font>?","Mulligan down to 6 cards?")]
        [TestCase("Choose<BR />[W] <unknown>literal</unknown>","Choose\n[W] <unknown>literal</unknown>")]
        public void FormattingDoesNotChangeEngineWordingOrUnknownTokens(string raw,string plain){Assert.That(OpeningHandFan.PlainPrompt(raw),Is.EqualTo(plain));}
        [TestCase(1,500)][TestCase(2,800)][TestCase(7,1200)][TestCase(10,900)][TestCase(20,640)]
        public void CardsRemainOrderedAndInsideTheHandSurface(int count,float width)
        {
            var cards=OpeningHandFan.Arrange(count,width);Assert.That(cards.Length,Is.EqualTo(count));
            float previous=float.NegativeInfinity;
            foreach(var card in cards){
                float angle=card.Angle*Mathf.Deg2Rad;
                float half=(card.Width*Mathf.Cos(angle)+card.Width*1.4f*Mathf.Abs(Mathf.Sin(angle)))*.5f;
                float center=card.Left+card.Width*.5f;
                Assert.That(center-half,Is.GreaterThanOrEqualTo(-.01f));Assert.That(center+half,Is.LessThanOrEqualTo(width+.01f));
                Assert.That(center,Is.GreaterThan(previous));previous=center;
            }
        }
        [Test] public void SevenCardOpeningHasTheReferenceFanComposition()
        {
            var cards=OpeningHandFan.Arrange(7,1200);
            Assert.That(cards[0].Angle,Is.LessThan(0));Assert.That(cards[6].Angle,Is.GreaterThan(0));Assert.That(cards[3].Angle,Is.Zero);
            Assert.That(cards[0].Top,Is.GreaterThan(cards[3].Top));Assert.That(cards[0].Top,Is.EqualTo(cards[6].Top).Within(.01f));
            Assert.That(cards[6].Angle-cards[0].Angle,Is.LessThanOrEqualTo(30));
        }
        [Test] public void SnapshotReorderingDrawAndReentryPreserveTheExistingHandOrder()
        {
            var order=new System.Collections.Generic.List<string>();
            GameplayCardLayout.RetainHandOrder(order,new[]{"first","second","third"});
            GameplayCardLayout.RetainHandOrder(order,new[]{"third","drawn","second","first"});
            Assert.That(order,Is.EqualTo(new[]{"first","second","third","drawn"}));
            GameplayCardLayout.RetainHandOrder(order,new[]{"drawn","third","first"});
            Assert.That(order,Is.EqualTo(new[]{"first","third","drawn"}));
            GameplayCardLayout.RetainHandOrder(order,new[]{"second","drawn","first","third"});
            Assert.That(order,Is.EqualTo(new[]{"first","third","drawn","second"}));
            GameplayCardLayout.RetainHandOrder(order,System.Array.Empty<string>());Assert.That(order,Is.Empty);
        }
        private static IReadOnlyList<ProjectedCard> Lands(int count,Action<JObject,int> edit=null)
        {
            var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
            var message=(JObject)corpus["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];var sample=snapshot["objects"][0].DeepClone();var cards=new JArray();
            snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["stack_targets"]=new JArray();snapshot["commanders"]=null;
            for(int i=0;i<count;i++){
                var card=(JObject)sample.DeepClone();card["object_id"]="land-"+i;card["presentation_id"]="visual-land-"+i;card["zone"]="battlefield";card["hidden"]=false;card["face_down"]=false;card["tapped"]=false;card["attachments"]=new JArray();card["attached_to"]=null;card["commander_id"]=null;card["damage"]=0;
                card["characteristics"]["name"]="Mountain";card["characteristics"]["type_line"]="Basic Land — Mountain";card["characteristics"]["counters"]=new JArray();card["characteristics"]["current_abilities"]=new JArray("{T}: Add {R}.");card["characteristics"]["transformed"]=false;card["characteristics"]["flipped"]=false;card["characteristics"]["is_copy"]=false;
                card["card_identity"]=new JObject{["oracle_id"]="mountain",["printing_id"]="different-art-"+i,["deck_entry_id"]=null};edit?.Invoke(card,i);cards.Add(card);
            }snapshot["objects"]=cards;
            return ViewerCardProjection.ParseSnapshot(message.ToString(),(string)snapshot["session_id"],(string)snapshot["viewer_id"],0,true).Cards;
        }
        [Test] public void MatchingLandsAcrossArtworkArePairedWithoutCombiningObjects()
        {
            var stacks=GameplayCardLayout.LandStacks(Lands(5));Assert.That(stacks.Select(p=>p.Count),Is.EqualTo(new[]{2,2,1}));
            Assert.That(stacks.SelectMany(p=>p).Select(c=>c.ObjectId).Distinct().Count(),Is.EqualTo(5));
        }
        [Test] public void LandPairsSeparateTapStateAndCounters()
        {
            var cards=Lands(6,(card,i)=>{card["tapped"]=i>=3;if(i==0)card["characteristics"]["counters"]=new JArray(new JArray("charge",1));});
            var stacks=GameplayCardLayout.LandStacks(cards);
            Assert.That(stacks.All(p=>p.Count<=2 && p.All(c=>c.Tapped==p[0].Tapped)),Is.True);
            Assert.That(stacks.Single(p=>p.Any(c=>c.ObjectId=="land-0")).Count,Is.EqualTo(1));
            Assert.That(stacks.Sum(p=>p.Count),Is.EqualTo(6));
        }
        [Test] public void CrowdedLandRowsShrinkAndPageWholePairs()
        {
            Assert.That(GameplayCardLayout.LandSize(8),Is.LessThan(GameplayCardLayout.LandSize(4)));Assert.That(GameplayCardLayout.LandSize(20),Is.LessThan(GameplayCardLayout.LandSize(8)));Assert.That(GameplayCardLayout.LandSize(10000),Is.GreaterThanOrEqualTo(62));
            var cards=Lands(40).Select(card=>(card:card,view:new CardView())).ToList();var pages=new Dictionary<string,int>();var navigation=new VisualElement();
            try{
                GameplayCardLayout.LandRow(cards,navigation,pages,()=>{},1280,500,260,855,110,"lands",new Vector2(550,730));
                var first=cards.Where(c=>c.view.style.display.value==DisplayStyle.Flex).Select(c=>c.card.ObjectId).ToArray();Assert.That(first.Length,Is.GreaterThan(0).And.LessThan(40));Assert.That(first.Length%2,Is.Zero);
                pages["lands"]=1;navigation.Clear();GameplayCardLayout.LandRow(cards,navigation,pages,()=>{},1280,500,260,855,110,"lands",new Vector2(550,730));
                var next=cards.Where(c=>c.view.style.display.value==DisplayStyle.Flex).Select(c=>c.card.ObjectId).ToArray();Assert.That(next.Intersect(first),Is.Empty);Assert.That(next.Length%2,Is.Zero);
            }finally{foreach(var item in cards)item.view.Dispose();}
        }
        [Test] public void EmptyHandDoesNotInventCards(){Assert.That(OpeningHandFan.Arrange(0,1200),Is.Empty);}
        [TestCase(-1,100)][TestCase(257,100)][TestCase(7,0)][TestCase(7,-1)]
        public void InvalidGeometryFailsExplicitly(int count,float width){Assert.Throws<System.ArgumentOutOfRangeException>(()=>OpeningHandFan.Arrange(count,width));}
    }
}
