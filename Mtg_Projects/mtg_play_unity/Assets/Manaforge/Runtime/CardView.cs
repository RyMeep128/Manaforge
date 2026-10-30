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
        private readonly ManaCostView mana = new ManaCostView();
        private readonly Image frame = new Image { name = "printing-frame", pickingMode = PickingMode.Ignore };
        private readonly CardPlate nameplate = new CardPlate("nameplate");
        private readonly CardPlate statplate = new CardPlate("pt-plate");
        private readonly CardPlate typeplate = new CardPlate("typeplate");
        private readonly VisualElement interior = new VisualElement { name = "frame-interior", pickingMode = PickingMode.Ignore };
        private readonly VisualElement printedStatsMask = new VisualElement { name = "printed-stats-mask", pickingMode = PickingMode.Ignore };
        private readonly VisualElement edge = new VisualElement { name = "card-edge", pickingMode = PickingMode.Ignore };
        private bool selected;
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
            interior.style.position=Position.Absolute;interior.style.backgroundColor=new Color(.88f,.88f,.80f);
            printedStatsMask.style.position=Position.Absolute;printedStatsMask.style.backgroundColor=new Color(.07f,.07f,.065f);
            Add(frame); Add(interior); Add(printedStatsMask); Add(artwork); Add(nameplate); Add(typeplate); Add(statplate); Add(missing); Add(title); Add(mana);
            Add(type); Add(rules); Add(stats); Add(status);
            edge.style.position=Position.Absolute;Add(edge);
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
            artwork.image = texture; frame.image = texture;
            missing.text = texture == null ? "Artwork unavailable" : "";
            Layout();
        }

        public void UpdateValues(CardDisplayValues values)
        {
            if (concealed) return;
            if (values == null) throw new ArgumentNullException(nameof(values));
            Set(title, values.Name); mana.SetCost(values.ManaCost); Set(type, values.TypeLine);
            Set(rules, values.RulesText); Set(stats, values.PowerToughness); Set(status, values.Status); Layout();
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

        // Selection draws over the card; it must not change the clipped content box when rotated.
        public void SetSelected(bool value){selected=!concealed && value;Layout();}

        private void Layout()
        {
            bool full = mode == CardPresentationMode.Full;
            bool hasStats = !string.IsNullOrEmpty(stats.text);
            style.width = width; style.height = width * (full ? 1.4f : .78f);
            float scale = width / 300f;
            style.borderTopLeftRadius=style.borderTopRightRadius=style.borderBottomLeftRadius=style.borderBottomRightRadius=width*.045f;
            Box(edge,0,0,100,100);
            float rim=full?0:Mathf.Max(1.5f,2*scale);
            edge.style.borderLeftWidth=edge.style.borderRightWidth=edge.style.borderBottomWidth=rim;
            edge.style.borderTopWidth=selected?Mathf.Max(3,rim):rim;
            edge.style.borderLeftColor=edge.style.borderRightColor=edge.style.borderBottomColor=new Color(.025f,.025f,.025f);
            edge.style.borderTopColor=selected?Color.cyan:new Color(.025f,.025f,.025f);
            edge.style.borderTopLeftRadius=edge.style.borderTopRightRadius=edge.style.borderBottomLeftRadius=edge.style.borderBottomRightRadius=width*.045f;
            edge.style.display=concealed?DisplayStyle.None:DisplayStyle.Flex;
            foreach(var label in new[]{title,type,rules,stats,status,missing}) {
                label.style.fontSize=(label==rules?12.8f:label==stats?23:label==status?10:18)*scale;
                label.style.backgroundColor=Color.clear;
                label.style.color=label==status?new Color(.85f,.85f,.81f):new Color(.06f,.065f,.055f);
                label.style.paddingLeft=label.style.paddingRight=label.style.paddingTop=label.style.paddingBottom=0;
                label.style.marginLeft=label.style.marginRight=label.style.marginTop=label.style.marginBottom=0;
            }
            title.style.unityFontStyleAndWeight=type.style.unityFontStyleAndWeight=stats.style.unityFontStyleAndWeight=FontStyle.Bold;
            title.style.whiteSpace=type.style.whiteSpace=stats.style.whiteSpace=WhiteSpace.NoWrap;
            title.style.unityTextAlign=type.style.unityTextAlign=TextAnchor.MiddleLeft;
            title.style.textOverflow=TextOverflow.Ellipsis; stats.style.unityTextAlign=TextAnchor.MiddleCenter;
            frame.style.position=artwork.style.position=Position.Absolute;
            Box(frame,0,0,100,100);frame.scaleMode=ScaleMode.StretchToFill;
            // Keep the exact printing's colored surround and original bevels, not a generic dark panel.
            frame.uv=full?new Rect(0,0,1,1):new Rect(0,.47f,1,.53f);
            frame.style.display=concealed || frame.image==null?DisplayStyle.None:DisplayStyle.Flex;
            // Preserve the printing footer: artist/collector credits start below the rules box.
            Box(interior,7,11,86,79);
            interior.style.display=!concealed && full && !authenticOnly?DisplayStyle.Flex:DisplayStyle.None;
            // The compact footer hides the underlying printing below the art window, including set symbols.
            Box(printedStatsMask,full?74:0,full?89:90,full?24:100,10);
            printedStatsMask.style.display=!concealed && !(full && authenticOnly) && (!full || hasStats)?DisplayStyle.Flex:DisplayStyle.None;
            Box(artwork,8,full?12:21,84,full?43:70);
            artwork.scaleMode=ScaleMode.StretchToFill;artwork.uv=artCrop;
            if(full && authenticOnly) {
                Box(artwork,0,0,100,100);artwork.uv=new Rect(0,0,1,1);artwork.scaleMode=ScaleMode.ScaleToFit;
            }
            Box(nameplate,5.5f,full?4:5,89,full?7:16);
            // Share the nameplate centerline; default Label margins otherwise shift small names.
            Box(title,8,full?4:5,full?Mathf.Max(40,84-mana.SymbolCount*6):84,full?7:16);
            Box(mana,57,4,34,7);mana.Resize(17*scale);
            Box(typeplate,5.5f,55.5f,89,7);Box(type,8,56,84,6);
            Box(rules,8,64,84,24);rules.style.backgroundColor=new Color(.88f,.88f,.80f);
            rules.style.paddingLeft=rules.style.paddingRight=4*scale;rules.style.paddingTop=3*scale;
            Box(statplate,75,full?90:79,22,full?8:19);
            Box(stats,77,full?90.3f:79.5f,18,full?7:17);
            Box(status,8,full?94:82,60,full?4:12);Box(missing,8,35,84,25);
            bool reconstructed=!concealed && !(full && authenticOnly);
            nameplate.style.display=reconstructed?DisplayStyle.Flex:DisplayStyle.None;
            typeplate.style.display=reconstructed && full?DisplayStyle.Flex:DisplayStyle.None;
            statplate.style.display=reconstructed && hasStats?DisplayStyle.Flex:DisplayStyle.None;
            mana.style.display=reconstructed && full?DisplayStyle.Flex:DisplayStyle.None;
            foreach(var label in new[]{title,type,rules,stats,status}) {
                bool show=reconstructed && (full || (label!=type && label!=rules));
                if(label==stats && string.IsNullOrEmpty(stats.text))show=false;
                if(label==status && (string.IsNullOrEmpty(status.text) || status.text=="PRINTED MOCK"))show=false;
                label.style.display=show?DisplayStyle.Flex:DisplayStyle.None;
            }
            missing.style.display=!concealed && artwork.image==null?DisplayStyle.Flex:DisplayStyle.None;
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
            selected = false;
            Identity = null;
            artwork.image = null; frame.image = null; mana.Conceal();
            foreach (var label in new[] { title, type, rules, stats, status, missing })
                label.text = "";
            tooltip = null;
            Layout();
        }

        public void Dispose() { Conceal(); RemoveFromHierarchy(); }
    }
}
