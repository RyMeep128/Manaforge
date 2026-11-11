using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayHudRegistryTests
    {
        private static JObject Fixture()=> (JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
        private static ProjectedDecisionFrame Frame(JObject envelope)
        {
            var snapshot=envelope["body"]["snapshot"];
            return ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),(string)snapshot["session_id"],(string)snapshot["viewer_id"],0,true);
        }
        [Test] public void RegistrationIsNonOwningAndDuplicateFailureIsAtomic()
        {
            using var registry=new GameplayHudRegistry();using var drawer=new GameplayDrawer("Extension");
            var parent=new VisualElement();parent.Add(drawer);
            var registration=registry.Register(new GameplayHudDescriptor("extension","Extension","test-slot",GameplayHudCapabilities.Drawer),drawer);
            Assert.Throws<InvalidOperationException>(()=>registry.Register(new GameplayHudDescriptor("extension","Duplicate","other"),new VisualElement()));
            Assert.That(registry.Count,Is.EqualTo(1));Assert.That(registry.Find("extension"),Is.SameAs(registration));
            registration.Available=false;Assert.That(registry.Count,Is.EqualTo(1));Assert.That(drawer.parent,Is.SameAs(parent));
            registration.Dispose();registration.Dispose();Assert.That(registry.Find("extension"),Is.Null);
            drawer.SetOpen(true);Assert.That(drawer.IsOpen,Is.True);Assert.That(drawer.parent,Is.SameAs(parent));
            using var replacement=registry.Register(new GameplayHudDescriptor("extension","Replacement","test-slot"),drawer);
            registration.Dispose();Assert.That(registry.Find("extension"),Is.SameAs(replacement));
            registry.Dispose();Assert.That(replacement.IsRegistered,Is.False);drawer.SetOpen(false);Assert.That(drawer.IsOpen,Is.False);
            Assert.Throws<ObjectDisposedException>(()=>registry.Register(new GameplayHudDescriptor("later","Later","test-slot"),drawer));
        }
        [Test] public void PlayerRegistrationsFollowSeatFormatAndViewerLifetime()
        {
            using var registry=new GameplayHudRegistry();var root=new VisualElement();
            using var surface=new ViewerCardSurface(root);using var hud=new GameplayPlayerHud(registry:registry);
            var envelope=Fixture();var snapshot=envelope["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();
            var frame=Frame(envelope);hud.Present(frame,surface,"freeform");
            string session=frame.Context.SessionId,viewer=frame.Context.ViewerId;
            string removed=frame.PlayerLifeTotals.Keys.First(id=>id!=viewer);
            var seat=registry.Find(GameplayHudIds.Seat(GameplayHudIds.Players,session,viewer,removed));
            Assert.That(seat.Element,Is.SameAs(hud.Player(removed)));
            var commander=registry.Find(GameplayHudIds.Seat(GameplayHudIds.Commanders,session,viewer,viewer));
            Assert.That(commander.Available,Is.False);Assert.That(registry.Find(GameplayHudIds.Commanders).Available,Is.False);
            hud.Present(frame,surface,"commander");Assert.That(commander.Available,Is.True);
            hud.Present(frame,surface,"freeform");Assert.That(commander.Available,Is.False);
            snapshot["viewer_id"]=removed;
            hud.Present(Frame(envelope),surface,"freeform");
            Assert.That(seat.IsRegistered,Is.False);Assert.That(commander.IsRegistered,Is.False);
            Assert.That(registry.Find(GameplayHudIds.Seat(GameplayHudIds.Players,session,removed,viewer)),Is.Not.Null);
            snapshot["viewer_id"]=viewer;hud.Present(Frame(envelope),surface,"freeform");
            seat=registry.Find(GameplayHudIds.Seat(GameplayHudIds.Players,session,viewer,removed));
            commander=registry.Find(GameplayHudIds.Seat(GameplayHudIds.Commanders,session,viewer,viewer));
            var players=(JArray)snapshot["players"];players.First(p=>(string)p["player_id"]==removed).Remove();
            snapshot["revision"]=(long)snapshot["revision"]+1;
            hud.Present(Frame(envelope),surface,"freeform");Assert.That(seat.IsRegistered,Is.False);
            Assert.That(registry.Entries.Count(e=>e.Descriptor.ParentId==GameplayHudIds.Players),Is.EqualTo(1));
            // A new session must never retain old seat keys, even with the same viewer/seat labels.
            snapshot["session_id"]="replacement-session";hud.Present(Frame(envelope),surface,"freeform");
            Assert.That(commander.IsRegistered,Is.False);
            Assert.That(registry.Find(GameplayHudIds.Seat(GameplayHudIds.Players,"replacement-session",viewer,viewer)),Is.Not.Null);
            hud.ClearPresentation();Assert.That(registry.Count,Is.EqualTo(2));
            hud.Dispose();Assert.That(registry.Count,Is.Zero);
        }
        [Test] public void ArenaRegistersFamiliesWithoutReparentingAndDisposesOnlyItsRegistry()
        {
            var root=new VisualElement();using var arena=new ArenaGameplayPresentation(root);
            var registry=arena.HudRegistry;
            foreach(string id in new[]{GameplayHudIds.Hand,GameplayHudIds.Players,GameplayHudIds.Commanders,
                GameplayHudIds.Priority,GameplayHudIds.Actions,GameplayHudIds.Zones,GameplayHudIds.Library,
                GameplayHudIds.Graveyard,GameplayHudIds.Exile,GameplayHudIds.Battlefield,GameplayHudIds.GameStack})
                Assert.That(registry.Find(id),Is.Not.Null,id);
            Assert.That(registry.Count,Is.EqualTo(11));
            Assert.That(registry.Find(GameplayHudIds.Hand).Element,Is.Null);
            Assert.That(registry.Find(GameplayHudIds.Zones).Element.name,Is.EqualTo("zones-drawer"));
            Assert.That(registry.Find(GameplayHudIds.Library).Element,Is.SameAs(root.Q<GameplayZonePanel>()));
            Assert.That(root.Q<GameplayDrawer>("zones-drawer").Content.Contains(root.Q<GameplayZonePanel>()),Is.True);
            Assert.That(arena.Capabilities.PrivateLayout || arena.Capabilities.SharedOrganization ||
                arena.Capabilities.VisualStacks || arena.Capabilities.AutomaticOrganization,Is.False);
            var extension=new VisualElement();root.Add(extension);
            registry.Register(new GameplayHudDescriptor("test-panel","Test panel","extension"),extension);
            arena.Dispose();Assert.That(registry.Count,Is.Zero);Assert.That(extension.parent,Is.SameAs(root));
        }
    }
}
