using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Bounded visual tokenization only. Unknown notation stays literal, and supplied tags are never rich text.
    public sealed class RulesTextView : VisualElement
    {
        private static readonly Regex Pieces=new Regex(@"\{[^{}]+\}|\r\n|\n|[ \t]+|[^\s{}]+|[{}]",RegexOptions.CultureInvariant);
        public string SourceText {get;private set;}="";
        public int SymbolCount {get;private set;}
        public RulesTextView()
        {
            name="rules-symbols";pickingMode=PickingMode.Ignore;style.position=Position.Absolute;
            style.flexDirection=FlexDirection.Row;style.flexWrap=Wrap.Wrap;
            style.alignItems=Align.FlexStart;style.alignContent=Align.FlexStart;style.overflow=Overflow.Hidden;
        }
        private static bool Known(string value)
        {
            if(!value.StartsWith("{") || !value.EndsWith("}"))return false;
            return ManaCostView.CanRenderSymbol(value.Substring(1,value.Length-2));
        }
        public void SetText(string value)
        {
            value=value??"";if(SourceText==value)return;Conceal();SourceText=value;
            var pieces=Pieces.Matches(value);
            if(pieces.Count>256 || Resources.Load<Font>("Mana")==null)return;
            bool hasSymbols=false;foreach(Match piece in pieces)hasSymbols|=Known(piece.Value);
            if(!hasSymbols)return;
            foreach(Match piece in pieces) {
                var text=piece.Value;VisualElement element;
                if(Known(text)){element=new ManaSymbolView(text.Substring(1,text.Length-2));SymbolCount++;}
                else if(text=="\n" || text=="\r\n") {
                    element=new VisualElement{pickingMode=PickingMode.Ignore};element.style.width=Length.Percent(100);element.style.height=0;
                } else if(string.IsNullOrWhiteSpace(text)) {
                    element=new VisualElement{pickingMode=PickingMode.Ignore,userData=text.Replace("\t","    ").Length};
                } else {
                    var label=new Label(text){enableRichText=false,pickingMode=PickingMode.Ignore};
                    label.style.color=new Color(.06f,.065f,.055f);label.style.whiteSpace=WhiteSpace.NoWrap;
                    label.style.paddingLeft=label.style.paddingRight=label.style.paddingTop=label.style.paddingBottom=0;
                    label.style.marginLeft=label.style.marginRight=label.style.marginTop=label.style.marginBottom=0;
                    label.style.unityTextAlign=TextAnchor.MiddleLeft;element=label;
                }
                element.style.flexShrink=0;Add(element);
            }
        }
        public void Resize(float size,FontStyle emphasis=FontStyle.Normal)
        {
            foreach(var child in Children()) {
                if(child is Label label){label.style.fontSize=size;label.style.height=size*1.35f;CardTypography.Apply(label,CardTextRole.Rules,emphasis);}
                else if(child is ManaSymbolView){child.style.width=child.style.height=size;child.style.marginTop=size*.175f;}
                else if(child.userData is int spaces){child.style.width=size*.28f*spaces;child.style.height=size*1.35f;}
            }
        }
        public void Conceal(){Clear();SourceText="";SymbolCount=0;tooltip=null;}
    }
}
