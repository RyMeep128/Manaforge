using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public enum CardPresentationMode { Compact, Full }

    // Immutable display input. Null means unavailable, not printed/default state.
    // This is a rendering projection, not a wire DTO or game model.
    public sealed class CardDisplayValues
    {
        public string Name { get; }
        public string ManaCost { get; }
        public string TypeLine { get; }
        public string RulesText { get; }
        public string PowerToughness { get; }
        public string Status { get; }
        public CardDisplayValues(string name, string manaCost, string typeLine,
            string rulesText, string powerToughness, string status)
        {
            Name = name; ManaCost = manaCost; TypeLine = typeLine;
            RulesText = rulesText; PowerToughness = powerToughness; Status = status;
        }
    }

    // UI Toolkit view, independent of seats, zones, input and game rules.
    // Textures are borrowed from the asset owner; this view never decodes/destroys them.
    public sealed class CardView : VisualElement, IDisposable
    {
        private readonly Image artwork = new Image { name = "artwork", pickingMode = PickingMode.Ignore };
        private readonly Label missing = Text("asset-status");
        private readonly Label title = Text("name");
        private readonly Label mana = Text("mana");
        private readonly Label type = Text("type");
        private readonly Label rules = Text("rules");
        private readonly Label stats = Text("stats");
        private readonly Label status = Text("status");
        private CardPresentationMode mode;
        private Rect artCrop;
        private bool authenticOnly;
        private bool concealed = true;
        private float width = 300;
        public CardVisualIdentity Identity { get; private set; }
        public Texture Artwork => artwork.image;
        public CardPresentationMode Mode => mode;

        public CardView()
        {
            name = "manaforge-card";
            style.position = Position.Relative;
            style.backgroundColor = new Color(0.09f, 0.11f, 0.13f);
            style.overflow = Overflow.Hidden;
            Add(artwork); Add(missing); Add(title); Add(mana);
            Add(type); Add(rules); Add(stats); Add(status);
            Conceal();
        }

        private static Label Text(string name)
        {
            var label = new Label { name = name, pickingMode = PickingMode.Ignore };
            label.enableRichText = false; // supplied text cannot inject tags or hide values
            label.style.position = Position.Absolute;
            label.style.whiteSpace = WhiteSpace.Normal;
            label.style.color = Color.white;
            label.style.overflow = Overflow.Hidden;
            return label;
        }

        // A new public identity clears prior per-object values before reuse.
        // Crop coordinates are supplied by a verified layout profile, not game rules.
        public void Bind(CardVisualIdentity identity, Texture texture, Rect crop)
        {
            if (identity == null) { Conceal(); return; }
            if (crop.x < 0 || crop.y < 0 || crop.width <= 0 || crop.height <= 0
                || crop.xMax > 1 || crop.yMax > 1
                || float.IsNaN(crop.x + crop.y + crop.width + crop.height))
                throw new ArgumentOutOfRangeException(nameof(crop));
            if (identity.MissingAsset && texture != null)
                throw new ArgumentException("Missing asset cannot bind an unrelated texture");
            Conceal();
            concealed = false;
            Identity = identity;
            authenticOnly = identity.LayoutProfileId == "authentic-image-v1";
            artCrop = crop;
            artwork.image = texture;
            missing.text = texture == null ? "Artwork unavailable" : "";
            Layout();
        }

        public void UpdateValues(CardDisplayValues values)
        {
            if (concealed) return;
            if (values == null) throw new ArgumentNullException(nameof(values));
            Set(title, values.Name); Set(mana, values.ManaCost); Set(type, values.TypeLine);
            Set(rules, values.RulesText); Set(stats, values.PowerToughness); Set(status, values.Status);
        }

        private static void Set(Label label, string value)
        {
            value = value ?? "";
            if (label.text != value) label.text = value;
        }

        public void SetPresentation(CardPresentationMode presentation, float newWidth)
        {
            if (presentation != CardPresentationMode.Compact && presentation != CardPresentationMode.Full)
                throw new ArgumentOutOfRangeException(nameof(presentation));
            if (float.IsNaN(newWidth) || float.IsInfinity(newWidth) || newWidth <= 0)
                throw new ArgumentOutOfRangeException(nameof(newWidth));
            mode = presentation; width = newWidth; Layout();
        }

        private void Layout()
        {
            bool full = mode == CardPresentationMode.Full;
            style.width = width;
            style.height = width * (full ? 1.4f : 0.78f);
            float scale = width / 300f;
            foreach (var label in new[] { title, mana, type, rules, stats, status, missing })
                label.style.fontSize = (label == rules ? 13 : 16) * scale;
            artwork.style.position = Position.Absolute;
            Box(artwork, 3, full ? 14 : 0, 94, full ? 42 : 100);
            artwork.scaleMode = ScaleMode.ScaleAndCrop;
            artwork.uv = artCrop;
            if (full && authenticOnly)
            {
                Box(artwork, 0, 0, 100, 100);
                artwork.uv = new Rect(0, 0, 1, 1);
                artwork.scaleMode = ScaleMode.ScaleToFit;
            }
            Box(title, 4, 3, 68, 10); Box(mana, 72, 3, 24, 10);
            Box(type, 4, 57, 92, 9); Box(rules, 4, 67, 92, 24);
            Box(stats, 70, 91, 26, 9); Box(status, 4, 91, 64, 9);
            if (!full) { Box(stats, 70, 76, 26, 22); Box(status, 4, 76, 64, 22); }
            Box(missing, 8, 35, 84, 25);
            foreach (var label in new[] { title, mana, type, rules, stats, status })
            {
                bool fullOnly = label == mana || label == type || label == rules;
                label.style.display = concealed || (full && authenticOnly) || (!full && fullOnly)
                    ? DisplayStyle.None : DisplayStyle.Flex;
                label.style.backgroundColor = new Color(0.04f, 0.05f, 0.06f, 0.90f);
            }
            missing.style.display = !concealed && artwork.image == null ? DisplayStyle.Flex : DisplayStyle.None;
        }

        private static void Box(VisualElement element, float x, float y, float w, float h)
        {
            element.style.left = Length.Percent(x); element.style.top = Length.Percent(y);
            element.style.width = Length.Percent(w); element.style.height = Length.Percent(h);
        }

        // Viewer handoff must call this before the next viewer is displayed.
        // The shared asset owner must separately revoke/destroy private cached textures.
        public void Conceal()
        {
            concealed = true;
            Identity = null;
            artwork.image = null;
            foreach (var label in new[] { title, mana, type, rules, stats, status, missing })
                label.text = "";
            tooltip = null;
            Layout();
        }

        public void Dispose() { Conceal(); RemoveFromHierarchy(); }
    }
}
