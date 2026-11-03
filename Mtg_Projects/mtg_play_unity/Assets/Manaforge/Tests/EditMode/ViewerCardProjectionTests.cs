using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerCardProjectionTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
        private static JObject Visible()=>(JObject)Corpus()["positive"][0]["envelope"];
        private static ProjectedCardFrame Project(JObject envelope)=>ViewerCardProjection.ParseSnapshot(envelope.ToString(),"fixture-0001","one",1,true);
        [Test] public void EverySharedSnapshotAndResultProjectsWithItsViewerAndRevision()
        {
            foreach(var test in Corpus()["positive"].Where(t=>(string)t["envelope"]["message_type"]!="event")) {
                var source=test["envelope"];var snapshot=source["body"]["snapshot"];
                var frame=ViewerCardProjection.ParseSnapshot(source.ToString(),(string)test["session"],(string)test["viewer"],(long)test["minimum_revision"],(bool)test["fixture_mode"]);
                Assert.That(frame.Context.ViewerId,Is.EqualTo((string)test["viewer"]));
                Assert.That(frame.Context.Revision,Is.EqualTo((long)snapshot["revision"]));
                Assert.That(frame.Cards.Count,Is.EqualTo(((JArray)snapshot["objects"]).Count));
                Assert.That(frame.Status,Is.EqualTo((string)snapshot["status"]));Assert.That(frame.Result,Is.EqualTo((string)snapshot["result"]));
                foreach(var card in frame.Cards)Assert.That(card.Context,Is.SameAs(frame.Context));
            }
        }
        [Test] public void SharedInvalidPrivateStaleAndWrongViewerInputsNeverReachTheProjection()
        {
            foreach(var test in Corpus()["negative"]) {
                var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>ViewerCardProjection.ParseSnapshot(test["envelope"].ToString(),(string)test["session"],(string)test["viewer"],(long)test["minimum_revision"],(bool)test["fixture_mode"]));
                Assert.That(error.Code,Is.EqualTo((string)test["code"]));Assert.That(error.Message,Is.EqualTo(error.Code));
            }
        }
        [Test] public void ConcealedObjectsKeepOnlyOpaqueRoutingWithoutDisplayOrRelationshipHints()
        {
            var source=Visible();var obj=source["body"]["snapshot"]["objects"][0];
            obj["hidden"]=true;obj["characteristics"]=JValue.CreateNull();obj["card_identity"]=JValue.CreateNull();
            obj["attachments"]=new JArray("opaque-other");obj["attached_to"]="opaque-parent";obj["tapped"]=true;obj["damage"]=9;
            var card=Project(source).Cards[0];Assert.That(card.Hidden,Is.True);Assert.That(card.ObjectId,Is.EqualTo((string)obj["object_id"]));
            Assert.That(card.Printing,Is.Null);Assert.That(card.Characteristics,Is.Null);Assert.That(card.Attachments,Is.Null);
            Assert.That(card.AttachedTo,Is.Null);Assert.That(card.Tapped,Is.Null);Assert.That(card.Damage,Is.Null);
        }
        [Test] public void NullableValuesAndExplicitZeroFalseAndEmptyRemainDistinct()
        {
            var source=Visible();var obj=source["body"]["snapshot"]["objects"][0];
            var unknown=Project(source).Cards[0];Assert.That(unknown.Tapped,Is.Null);Assert.That(unknown.Characteristics.Counters,Is.Null);
            obj["tapped"]=false;obj["damage"]=0;obj["face_down"]=false;obj["attachments"]=new JArray();
            obj["characteristics"]["counters"]=new JArray();obj["characteristics"]["current_abilities"]=new JArray();
            var known=Project(source).Cards[0];Assert.That(known.Tapped,Is.False);Assert.That(known.Damage,Is.Zero);Assert.That(known.FaceDown,Is.False);
            Assert.That(known.Characteristics.Counters,Is.Empty);Assert.That(known.Characteristics.CurrentAbilities,Is.Empty);Assert.That(known.Attachments,Is.Empty);
            Assert.That(known.Characteristics.EngineViewText,Is.Null);
        }
        [Test] public void CurrentCharacteristicsPrintingAndUnsupportedTextRemainIndependent()
        {
            var source=Visible();var obj=source["body"]["snapshot"]["objects"][0];
            obj["card_identity"]=new JObject{["oracle_id"]="oracle",["printing_id"]="exact-printing",["deck_entry_id"]="not-a-renderer-field"};
            var c=obj["characteristics"];c["name"]="Current copy name";c["power"]="*";c["toughness"]=JValue.CreateNull();
            c["is_copy"]=true;c["transformed"]=true;c["flipped"]=false;c["loyalty"]="0";c["defense"]="7";
            c["engine_view_text"]=new JArray("Engine presentation <b>literal</b>");c["current_abilities"]=new JArray("Supplied ability");
            c["counters"]=JArray.Parse("[[\"charge\",2]]");
            var card=Project(source).Cards[0];Assert.That(card.Printing.PrintingId,Is.EqualTo("exact-printing"));
            Assert.That(card.Characteristics.Name,Is.EqualTo("Current copy name"));Assert.That(card.Characteristics.Power,Is.EqualTo("*"));
            Assert.That(card.Characteristics.Toughness,Is.Null);Assert.That(card.Characteristics.Loyalty,Is.EqualTo("0"));
            Assert.That(card.Characteristics.Defense,Is.EqualTo("7"));Assert.That(card.Characteristics.IsCopy,Is.True);
            Assert.That(card.Characteristics.EngineViewText[0],Is.EqualTo("Engine presentation <b>literal</b>"));
            Assert.That(card.Characteristics.UnsupportedFields,Does.Contain("current_rules_text"));
            Assert.That(card.Characteristics.Counters[0].Amount,Is.EqualTo(2));
        }
        [Test] public void AllCollectionsAreReadOnlyAndNoJsonOrMutableDtoEscapes()
        {
            var source=Visible();var obj=source["body"]["snapshot"]["objects"][0];obj["attachments"]=new JArray("permitted-object");
            var frame=Project(source);var card=frame.Cards[0];
            Assert.Throws<NotSupportedException>(()=>((IList<ProjectedCard>)frame.Cards).Clear());
            Assert.Throws<NotSupportedException>(()=>((IList<string>)card.Attachments)[0]="changed");
            Assert.Throws<NotSupportedException>(()=>((IList<string>)card.Characteristics.UnsupportedFields).Clear());
            obj["characteristics"]["name"]="Later mutation";obj["attachments"][0]="different";
            Assert.That(card.Characteristics.Name,Is.EqualTo("Synthetic Fixture Card"));Assert.That(card.Attachments[0],Is.EqualTo("permitted-object"));
            foreach(var type in new[]{typeof(ProjectedCard),typeof(ProjectedCharacteristics),typeof(ProjectedPrinting),typeof(ProjectedCounter),typeof(CardProjectionContext),typeof(ProjectedCardFrame)}) {
                Assert.That(type.GetFields(),Is.Empty);
                foreach(var property in type.GetProperties()){Assert.That(property.GetSetMethod(),Is.Null);Assert.That(typeof(JToken).IsAssignableFrom(property.PropertyType),Is.False);}
            }
        }
        [Test] public void EventsCannotMasqueradeAsCompleteCardFrames()
        {
            var test=Corpus()["positive"].Single(t=>(string)t["envelope"]["message_type"]=="event");
            var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>ViewerCardProjection.ParseSnapshot(test["envelope"].ToString(),(string)test["session"],(string)test["viewer"],(long)test["minimum_revision"],(bool)test["fixture_mode"]));
            Assert.That(error.Code,Is.EqualTo("PROJECTION_SNAPSHOT_REQUIRED"));
        }
        [TestCase("", "viewer",0)] [TestCase("session","",0)] [TestCase("session","viewer",-1)]
        public void MissingTrustedContextFailsBeforeReadingCardData(string session,string viewer,long revision)
        {
            var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>ViewerCardProjection.ParseSnapshot("not json",session,viewer,revision));
            Assert.That(error.Code,Is.EqualTo("PROJECTION_CONTEXT"));
        }
    }
}
