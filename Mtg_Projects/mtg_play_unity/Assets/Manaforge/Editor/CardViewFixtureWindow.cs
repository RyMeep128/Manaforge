using System;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Editor
{
    // Explicit mock projection. No real artwork, engine state, game actions or deck data.
    public sealed class CardViewFixtureWindow : EditorWindow
    {
        private CardView full;
        private CardView compact;
        private bool changed;

        [MenuItem("Window/Manaforge/Card component fixture")]
        public static void Open() => GetWindow<CardViewFixtureWindow>("Mock card components");

        public void CreateGUI()
        {
            rootVisualElement.Add(new Label("MOCK COMPONENT FIXTURE — artwork unavailable; no engine connected"));
            rootVisualElement.Add(new Button(() => { changed = !changed; Refresh(); })
                { text = "Toggle supplied mock P/T and rules" });
            var row = new VisualElement();
            row.style.flexDirection = FlexDirection.Row;
            rootVisualElement.Add(row);
            full = Make(CardPresentationMode.Full, 360);
            compact = Make(CardPresentationMode.Compact, 240);
            row.Add(full); row.Add(compact);
            Refresh();
        }

        private static CardView Make(CardPresentationMode mode, float width)
        {
            var view = new CardView();
            var identity = VisualPrintingPolicy.Resolve(false,
                new VisualPrintingCandidate("mock-oracle", "mock-printing", "mock-front", true, false),
                Array.Empty<VisualPrintingCandidate>());
            view.Bind(identity, null, new Rect(0, 0, 1, 1));
            view.SetPresentation(mode, width);
            return view;
        }

        private void Refresh()
        {
            var values = new CardDisplayValues("Explicit mock creature", "{X}{G}",
                "Creature — Fixture", changed ? "Supplied mock flying.\nSecond paragraph." : "Explicit mock rules text.",
                changed ? "5/5" : "2/2", changed ? "2 counters" : "");
            full?.UpdateValues(values); compact?.UpdateValues(values);
        }

        private void OnDisable() { full?.Dispose(); compact?.Dispose(); }
    }
}
