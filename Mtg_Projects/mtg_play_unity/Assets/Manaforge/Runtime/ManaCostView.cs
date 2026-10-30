using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Presentation of supplied notation only. No mana accounting or payment decisions.
    public sealed class ManaCostView : VisualElement
    {
        private static readonly Regex Tokens = new Regex(@"\{([^{}]+)\}", RegexOptions.CultureInvariant);
        private static Font font;
        private float size = 17;
        public string Cost { get; private set; } = "";
        public int SymbolCount { get; private set; }
        public ManaCostView()
        {
            name = "mana"; pickingMode = PickingMode.Ignore;
            style.position = Position.Absolute; style.flexDirection = FlexDirection.Row;
            style.justifyContent = Justify.FlexEnd; style.alignItems = Align.Center;
        }
        public static bool TryGlyph(string token, out char glyph)
        {
            if(string.IsNullOrEmpty(token)){glyph='\0';return false;}
            const string colors = "WUBRG"; int color = colors.IndexOf(token, StringComparison.Ordinal);
            if(token.Length == 1 && color >= 0){glyph = (char)(0xe600 + color);return true;}
            if(int.TryParse(token, out int number) && number >= 0 && number <= 20 && token == number.ToString())
            {glyph = (char)(number < 16 ? 0xe605 + number : number == 16 ? 0xe62a : number == 17 ? 0xe62b : number == 18 ? 0xe62c : number == 19 ? 0xe62d : 0xe62e);return true;}
            switch(token){case "X":glyph='\ue615';return true;case "Y":glyph='\ue616';return true;case "Z":glyph='\ue617';return true;
                case "P":glyph='\ue618';return true;case "S":glyph='\ue619';return true;case "C":glyph='\ue904';return true;default:glyph='\0';return false;}
        }
        private static Color ColorFor(string token)
        {
            switch(token){case "W":return new Color(.98f,.96f,.80f);case "U":return new Color(.65f,.81f,.91f);
                case "B":return new Color(.67f,.62f,.65f);case "R":return new Color(.93f,.57f,.43f);case "G":return new Color(.59f,.76f,.61f);
                default:return new Color(.79f,.77f,.72f);}
        }
        public void SetCost(string value)
        {
            value = value ?? ""; if(Cost == value)return;
            Clear(); Cost = value; SymbolCount = 0; tooltip = value;
            var tokens = Tokens.Matches(value);
            if(tokens.Count > 32 || Tokens.Replace(value, "") != "") {Fallback(value);return;}
            if(font == null)font = Resources.Load<Font>("Mana");
            foreach(Match match in tokens)
            {
                string token = match.Groups[1].Value;
                var parts = token.Split('/');
                bool hybrid = parts.Length == 2 && TryGlyph(parts[0],out _) && TryGlyph(parts[1],out _);
                if(font == null || (!TryGlyph(token,out _) && !hybrid)){Fallback(value);return;}
                var symbol = new VisualElement { name = "mana-symbol", pickingMode = PickingMode.Ignore };
                symbol.style.backgroundColor = ColorFor(hybrid ? parts[0] : token);
                symbol.style.borderTopLeftRadius = symbol.style.borderTopRightRadius = symbol.style.borderBottomLeftRadius = symbol.style.borderBottomRightRadius = 100;
                symbol.style.borderBottomWidth = 1; symbol.style.borderBottomColor = new Color(.08f,.07f,.06f,.9f);
                if(hybrid){Glyph(symbol,parts[0],true,false);Glyph(symbol,parts[1],true,true);}
                else Glyph(symbol,token,false,false);
                Add(symbol);SymbolCount++;
            }
            Resize(size);
        }
        private void Fallback(string value)
        {
            Clear();SymbolCount=0;var label=new Label(value){enableRichText=false,pickingMode=PickingMode.Ignore};
            label.style.color=Color.black;Add(label);Resize(size);
        }
        private static void Glyph(VisualElement parent,string token,bool hybrid,bool second)
        {
            TryGlyph(token,out char glyph);var label=new Label(glyph.ToString()){enableRichText=false,pickingMode=PickingMode.Ignore};
            label.style.unityFontDefinition = new FontDefinition { font = font };
            label.style.color=new Color(.08f,.07f,.06f);label.style.unityTextAlign=TextAnchor.MiddleCenter;
            label.style.position=Position.Absolute;label.style.left=Length.Percent(hybrid?(second?45:0):0);
            label.style.top=Length.Percent(hybrid?(second?42:0):0);label.style.width=Length.Percent(hybrid?55:100);label.style.height=Length.Percent(hybrid?58:100);
            label.style.paddingLeft=label.style.paddingRight=label.style.paddingTop=label.style.paddingBottom=0;
            label.style.marginLeft=label.style.marginRight=label.style.marginTop=label.style.marginBottom=0;
            label.style.unityFontStyleAndWeight=FontStyle.Normal;
            label.userData=hybrid;parent.Add(label);
        }
        public void Resize(float value)
        {
            size=value;
            foreach(var child in Children())
            {
                if(child is Label fallback){fallback.style.fontSize=size;continue;}
                child.style.width=size;child.style.height=size;child.style.flexShrink=0;child.style.marginLeft=size*.12f;
                foreach(var label in child.Query<Label>().ToList())label.style.fontSize=size*(label.userData is bool hybrid && hybrid ? .56f : .88f);
            }
        }
        public void Conceal(){Clear();Cost="";SymbolCount=0;tooltip=null;}
    }
}
