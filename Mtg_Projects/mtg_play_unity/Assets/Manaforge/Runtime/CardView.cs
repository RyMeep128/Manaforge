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
        public CardCompactProfile CompactProfile {get;}
        public string Loyalty {get;}
        public string Defense {get;}
        public FontStyle RulesStyle {get;}
        public string CollectorText {get;}
        public CardDisplayValues(string name, string manaCost, string typeLine,
            string rulesText, string powerToughness, string status, CardCompactProfile compactProfile=null, string loyalty=null,string defense=null,FontStyle rulesStyle=FontStyle.Normal,string collectorText=null)
        {
            Name = name; ManaCost = manaCost; TypeLine = typeLine;
            RulesText = rulesText; PowerToughness = powerToughness; Status = status;
            CompactProfile=compactProfile;Loyalty=loyalty;Defense=defense;RulesStyle=rulesStyle;CollectorText=collectorText;
        }
    }

    // UI Toolkit view, independent of seats, zones, input and game rules.
    // Textures are borrowed from the asset owner; this view never decodes/destroys them.
    public sealed class CardView : VisualElement, IDisposable
    {
        private readonly Image artwork = new Image { name = "artwork", pickingMode = PickingMode.Ignore };
        private readonly VisualElement artWindow=new VisualElement {name="art-window",pickingMode=PickingMode.Ignore};
        private readonly VisualElement secondWindow=new VisualElement {name="second-art-window",pickingMode=PickingMode.Ignore};
        private readonly Image secondArt=new Image {name="second-artwork",pickingMode=PickingMode.Ignore};
        private readonly BattlefieldFrame miniSurround=new BattlefieldFrame();
        private readonly LoyaltyCounterView loyaltyCounter=new LoyaltyCounterView();
        private readonly Label miniKind=Text("mini-kind");
        private CardCompactProfile compactProfile;
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
        private readonly RulesTextView rulesSymbols = new RulesTextView();
        private readonly Label stats = Text("stats");
        private readonly Label status = Text("status");
        private readonly Label collector=Text("collector");
        private FontStyle rulesEmphasis;
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
            artWindow.style.position=secondWindow.style.position=Position.Absolute;
            artWindow.style.overflow=secondWindow.style.overflow=Overflow.Hidden;
            artWindow.Add(artwork);secondWindow.Add(secondArt);
            Add(frame);Add(miniSurround); Add(interior); Add(printedStatsMask); Add(artWindow);Add(secondWindow); Add(nameplate); Add(typeplate); Add(statplate); Add(missing); Add(title); Add(mana);
            Add(type); Add(rules); Add(rulesSymbols); Add(stats); Add(status);Add(miniKind);Add(loyaltyCounter);Add(collector);
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
            artwork.image = texture; frame.image = texture;secondArt.image=texture;
            missing.text = texture == null ? "Artwork unavailable" : "";
            Layout();
        }

        public void UpdateValues(CardDisplayValues values)
        {
            if (concealed) return;
            if (values == null) throw new ArgumentNullException(nameof(values));
            Set(title, values.Name); mana.SetCost(values.ManaCost); Set(type, values.TypeLine);
            compactProfile=values.CompactProfile;
            authenticOnly=Identity?.LayoutProfileId=="authentic-image-v1" || !string.IsNullOrEmpty(compactProfile?.Kind);
            Set(rules, values.RulesText); rulesSymbols.SetText(values.RulesText);
            Set(stats,values.PowerToughness ?? values.Defense);loyaltyCounter.SetValue(values.Loyalty);
            Set(status, values.Status);Set(miniKind,compactProfile?.Kind);Set(collector,values.CollectorText);rulesEmphasis=values.RulesStyle; Layout();
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
            bool imageFallback=authenticOnly && (full || compactProfile==null);
            int inspectionRotation=full && authenticOnly?(compactProfile?.InspectionRotation??0):0;
            bool hasStats = !string.IsNullOrEmpty(stats.text);
            style.width = width;
            style.height = full && authenticOnly && artwork.image!=null
                ? (inspectionRotation==90?width*artwork.image.width/artwork.image.height:width*artwork.image.height/artwork.image.width) : width*(full?1.4f:BattlefieldFrame.Aspect);
            float scale = width / 300f;
            style.borderTopLeftRadius=style.borderTopRightRadius=style.borderBottomLeftRadius=style.borderBottomRightRadius=width*.03f;
            Box(edge,0,0,100,100);
            float rim=full?0:Mathf.Max(1.5f,2*scale);
            edge.style.borderLeftWidth=edge.style.borderRightWidth=edge.style.borderBottomWidth=rim;
            // The upper printing surround is narrow; do not cover it with the heavier lower rim.
            float topRim=full?0:Mathf.Max(.75f,.9f*scale);
            edge.style.borderTopWidth=selected?Mathf.Max(1.5f,topRim):topRim;
            edge.style.borderLeftColor=edge.style.borderRightColor=edge.style.borderBottomColor=new Color(.025f,.025f,.025f);
            edge.style.borderTopColor=selected?Color.cyan:new Color(.025f,.025f,.025f);
            edge.style.borderTopLeftRadius=edge.style.borderTopRightRadius=edge.style.borderBottomLeftRadius=edge.style.borderBottomRightRadius=width*.03f;
            edge.style.display=concealed?DisplayStyle.None:DisplayStyle.Flex;
            foreach(var label in new[]{title,type,rules,stats,status,missing,miniKind}) {
                label.style.fontSize=(label==rules?12.8f:label==stats?23:label==status?10:18)*scale;
                label.style.backgroundColor=Color.clear;
                label.style.color=label==status || label==miniKind?new Color(.85f,.85f,.81f):new Color(.06f,.065f,.055f);
                label.style.paddingLeft=label.style.paddingRight=label.style.paddingTop=label.style.paddingBottom=0;
                label.style.marginLeft=label.style.marginRight=label.style.marginTop=label.style.marginBottom=0;
            }
            title.style.unityFontStyleAndWeight=type.style.unityFontStyleAndWeight=stats.style.unityFontStyleAndWeight=FontStyle.Bold;
            title.style.whiteSpace=type.style.whiteSpace=stats.style.whiteSpace=WhiteSpace.NoWrap;
            title.style.unityTextAlign=type.style.unityTextAlign=TextAnchor.MiddleLeft;
            title.style.textOverflow=TextOverflow.Ellipsis; stats.style.unityTextAlign=TextAnchor.MiddleCenter;
            CardTypography.Apply(title,CardTextRole.Title);CardTypography.Apply(type,CardTextRole.Type);
            CardTypography.Apply(stats,CardTextRole.PowerToughness);CardTypography.Apply(rules,CardTextRole.Rules,rulesEmphasis);
            CardTypography.Apply(collector,CardTextRole.Collector);collector.style.fontSize=8*scale;
            Box(collector,8,94,84,4);collector.style.color=Color.white;collector.style.backgroundColor=new Color(.04f,.04f,.035f);
            collector.style.display=!concealed && full && !authenticOnly && !string.IsNullOrEmpty(collector.text)?DisplayStyle.Flex:DisplayStyle.None;
            frame.style.position=artwork.style.position=Position.Absolute;
            Box(frame,0,0,100,100);frame.scaleMode=ScaleMode.StretchToFill;
            // Keep the exact printing's colored surround and original bevels, not a generic dark panel.
            frame.uv=full?new Rect(0,0,1,1):new Rect(0,.47f,1,.53f);
            frame.style.display=concealed || authenticOnly || frame.image==null?DisplayStyle.None:DisplayStyle.Flex;
            Box(miniSurround,0,0,100,100);miniSurround.style.display=!concealed && !full && authenticOnly && compactProfile!=null?DisplayStyle.Flex:DisplayStyle.None;
            // Preserve the printing footer: artist/collector credits start below the rules box.
            // Standard-frame inner textbox ends before the collector footer at about 92.3%.
            // Stay inside the printed vertical outline rather than painting over its right edge.
            Box(interior,7.6f,11,84.8f,81.3f);
            interior.style.display=!concealed && full && !authenticOnly?DisplayStyle.Flex:DisplayStyle.None;
            // The compact footer hides the underlying printing below the art window, including set symbols.
            Box(printedStatsMask,full?74:0,full?89:94,full?24:100,10);
            printedStatsMask.style.display=!concealed && !imageFallback && (!full || hasStats)?DisplayStyle.Flex:DisplayStyle.None;
            float height=style.height.value.value;
            bool split=!full && !imageFallback && compactProfile?.SecondaryCrop!=null;
            Rect area=imageFallback?new Rect(0,0,100,100):new Rect(full?8:4,full?12:21,split?45:full?84:92,full?43:73);
            Rect crop=imageFallback?new Rect(0,0,1,1):!full && compactProfile!=null?compactProfile.Crop:artCrop;
            int rotation=imageFallback?inspectionRotation:!full?(compactProfile?.Rotation??0):0;
            LayoutArtwork(artWindow,artwork,area,crop,rotation,width,height,imageFallback || (!full && compactProfile?.Kind=="Dungeon"));
            secondWindow.style.display=!concealed && split?DisplayStyle.Flex:DisplayStyle.None;
            if(split)LayoutArtwork(secondWindow,secondArt,new Rect(51,21,45,73),compactProfile.SecondaryCrop.Value,compactProfile.Rotation,width,height,false);
            artWindow.style.display=concealed?DisplayStyle.None:DisplayStyle.Flex;
            Box(nameplate,full?5.5f:3,full?4:5,full?89:94,full?7:16);
            // Share the nameplate centerline; default Label margins otherwise shift small names.
            Box(title,full?8:5,full?4:5,full?Mathf.Max(40,84-mana.SymbolCount*6):90,full?7:16);
            Box(mana,57,4,34,7);mana.Resize(20*scale);
            Box(typeplate,5.5f,55.5f,89,7);Box(type,8,56,84,6);
            Box(rules,8,64,84,24);rules.style.backgroundColor=new Color(.88f,.88f,.80f);
            rules.style.paddingLeft=rules.style.paddingRight=4*scale;rules.style.paddingTop=3*scale;
            Box(rulesSymbols,8,64,84,24);rulesSymbols.style.paddingLeft=rulesSymbols.style.paddingRight=4*scale;rulesSymbols.style.paddingTop=3*scale;
            rulesSymbols.Resize(12.8f*scale,rulesEmphasis);rules.style.opacity=rulesSymbols.SymbolCount>0?0:1;
            rulesSymbols.style.display=!concealed && full && !authenticOnly && rulesSymbols.SymbolCount>0?DisplayStyle.Flex:DisplayStyle.None;
            Box(statplate,75,full?90:79,22,full?8:19);
            Box(stats,77,full?90.3f:79.5f,18,full?7:17);
            Box(status,8,full?94:82,60,full?4:12);Box(missing,8,35,84,25);
            Box(miniKind,8,91,65,8);miniKind.style.fontSize=12*scale;miniKind.style.display=DisplayStyle.None;
            Box(loyaltyCounter,39,79,22,20);loyaltyCounter.Resize(28*scale);
            loyaltyCounter.style.display=!concealed && !full && !imageFallback && !string.IsNullOrEmpty(loyaltyCounter.Value)?DisplayStyle.Flex:DisplayStyle.None;
            bool reconstructed=!concealed && !imageFallback;
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

        private static void LayoutArtwork(VisualElement window,Image image,Rect area,Rect uv,int rotation,float width,float height,bool fit)
        {
            Box(window,area.x,area.y,area.width,area.height);image.style.position=Position.Absolute;
            float w=width*area.width/100f,h=height*area.height/100f;
            if(rotation==90) {
                image.style.left=(w-h)/2;image.style.top=(h-w)/2;image.style.width=h;image.style.height=w;
            }else Box(image,0,0,100,100);
            image.style.rotate=new Rotate(new Angle(rotation));image.uv=uv;
            image.scaleMode=fit?ScaleMode.ScaleToFit:ScaleMode.ScaleAndCrop;
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
            artwork.image = null;secondArt.image=null; frame.image = null;compactProfile=null;miniKind.text="";loyaltyCounter.SetValue(null); mana.Conceal(); rulesSymbols.Conceal();
            rulesEmphasis=FontStyle.Normal;
            foreach (var label in new[] { title, type, rules, stats, status, missing,collector })
                label.text = "";
            tooltip = null;
            Layout();
        }

        public void Dispose() { Conceal(); RemoveFromHierarchy(); }
    }
}
