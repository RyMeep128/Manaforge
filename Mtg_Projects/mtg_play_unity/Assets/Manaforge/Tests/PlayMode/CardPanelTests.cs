using System;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class CardPanelTests
    {
        private GameObject host;
        private PanelSettings settings;
        private Texture2D texture;
        private CardView view;
        private UIDocument document;

        [UnitySetUp]
        public IEnumerator Setup()
        {
            settings = ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet = Resources.Load<ThemeStyleSheet>("CardTheme");
            Assert.That(settings.themeStyleSheet, Is.Not.Null, "Runtime text requires an imported default theme");
            settings.scaleMode = PanelScaleMode.ConstantPixelSize;
            settings.scale = 1;
            host = new GameObject("Owned card panel test");
            document = host.AddComponent<UIDocument>();
            document.panelSettings = settings;
            document.rootVisualElement.style.width = 800;
            document.rootVisualElement.style.height = 600;
            texture = new Texture2D(4, 4);
            view = new CardView();
            document.rootVisualElement.Add(view);
            view.Bind(Identity("first"), texture, new Rect(0, 0, 1, 1));
            view.SetPresentation(CardPresentationMode.Full, 300);
            view.UpdateValues(Values("Private first viewer", "2/2"));
            yield return null;
            yield return null;
        }

        private static CardVisualIdentity Identity(string printing) =>
            VisualPrintingPolicy.Resolve(false,
                new VisualPrintingCandidate("mock-oracle", printing, "mock-front", true, true),
                Array.Empty<VisualPrintingCandidate>());
        private static CardDisplayValues Values(string name, string pt) =>
            new CardDisplayValues(name, "{G}", "Creature — Mock", "Explicit mock rules", pt, "");

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            view?.Dispose();
            UnityEngine.Object.Destroy(host);
            UnityEngine.Object.Destroy(settings);
            UnityEngine.Object.Destroy(texture);
            yield return null;
        }

        [UnityTest]
        public IEnumerator AttachedPanelResolvesFullAndCompactGeometryWithoutReplacingTexture()
        {
            Assert.That(view.panel, Is.Not.Null);
            Assert.That(view.resolvedStyle.width, Is.EqualTo(300).Within(0.1));
            Assert.That(view.resolvedStyle.height, Is.EqualTo(420).Within(0.1));
            Assert.That(view.Q<Label>("rules").resolvedStyle.display, Is.EqualTo(DisplayStyle.Flex));
            view.SetPresentation(CardPresentationMode.Compact, 240);
            view.UpdateValues(Values("Same object", "5/5"));
            yield return null;
            yield return null;
            Assert.That(view.resolvedStyle.width, Is.EqualTo(240).Within(0.1));
            Assert.That(view.resolvedStyle.height, Is.EqualTo(Mathf.Round(240 * 0.78f)).Within(0.1));
            Assert.That(view.Q<Label>("rules").resolvedStyle.display, Is.EqualTo(DisplayStyle.None));
            Assert.That(view.Q<Label>("stats").text, Is.EqualTo("5/5"));
            Assert.That(view.Artwork, Is.SameAs(texture));
        }

        [UnityTest]
        public IEnumerator FixturePointerSelectionTapTargetAndCleanupUseOnlyDisplayObjects()
        {
            var second = new CardView();
            document.rootVisualElement.Add(second);
            second.Bind(Identity("second"), texture, new Rect(0, 0, 1, 1));
            yield return null; yield return null;
            var contentBeforeSelection=second.contentRect;
            int inspected = -1;
            var interactions = new FixtureInteractions(document.rootVisualElement, new[] { view, second }, index => inspected = index);
            try
            {
                using (var click = PointerDownEvent.GetPooled(new Event { type = EventType.MouseDown, button = 0, mousePosition = second.worldBound.center })) { click.target = second; second.SendEvent(click); }
                Assert.That(interactions.SelectedIndex, Is.EqualTo(1));
                Assert.That(inspected, Is.EqualTo(1));
                interactions.ToggleSelectedTap();
                Assert.That(interactions.IsTapped(1), Is.True);
                interactions.TargetNext();
                Assert.That(interactions.TargetIndex, Is.Zero);
                yield return null; yield return null;
                Assert.That(second.resolvedStyle.rotate.angle.value, Is.EqualTo(90));
                Assert.That(second.contentRect,Is.EqualTo(contentBeforeSelection),"Selection must not move artwork inside the rotated clip");
                interactions.ToggleSelectedTap();
                Assert.That(interactions.IsTapped(1), Is.False);
                interactions.Select(0);
                Assert.That(interactions.TargetIndex, Is.EqualTo(-1));
            }
            finally { interactions.Dispose(); second.Dispose(); }
            using (var click = PointerDownEvent.GetPooled(new Event { type = EventType.MouseDown, button = 0 })) { click.target = view; view.SendEvent(click); }
            Assert.That(interactions.SelectedIndex, Is.EqualTo(-1), "Disposed callbacks cannot retain a selection");
            Assert.Throws<ObjectDisposedException>(() => interactions.Select(0));
        }

        [UnityTest]
        public IEnumerator ViewerHandoffHasAnEmptyFrameBeforeRebindingAndDisposeDetaches()
        {
            view.tooltip = "Private first viewer tooltip";
            view.Conceal();
            yield return null;
            Assert.That(view.Identity, Is.Null);
            Assert.That(view.Artwork, Is.Null);
            Assert.That(view.tooltip, Is.Null.Or.Empty);
            foreach (var label in view.Query<Label>().ToList())
            {
                Assert.That(label.text, Is.Empty);
                Assert.That(label.resolvedStyle.display, Is.EqualTo(DisplayStyle.None));
            }
            view.Bind(Identity("second"), texture, new Rect(0, 0, 1, 1));
            yield return null;
            Assert.That(view.Q<Label>("name").text, Is.Empty, "No previous-viewer text survives rebinding");
            view.UpdateValues(Values("Second viewer", "3/3"));
            Assert.That(view.Identity.SelectedPrintingId, Is.EqualTo("second"));
            view.Dispose();
            yield return null;
            Assert.That(view.panel, Is.Null);
            Assert.That(view.parent, Is.Null);
            Assert.That(view.Artwork, Is.Null);
            Assert.That(texture == null, Is.False, "Shared asset owner retains texture lifetime");
        }
    }
}
