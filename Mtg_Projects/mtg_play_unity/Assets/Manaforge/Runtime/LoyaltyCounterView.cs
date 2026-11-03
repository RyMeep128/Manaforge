using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Normalized planar silhouette of supplied Card_Loyalty mesh, path ID 5550224334418384154.
    public sealed class LoyaltyCounterView : VisualElement
    {
        private static readonly Vector2[] Outline={new Vector2(0,.2067f),new Vector2(.0954f,.757f),new Vector2(.5f,1),
            new Vector2(.9046f,.757f),new Vector2(1,.2067f),new Vector2(.628f,0),new Vector2(.372f,0)};
        private readonly Label number=new Label{name="loyalty-value",enableRichText=false,pickingMode=PickingMode.Ignore};
        public string Value=>number.text;
        public LoyaltyCounterView()
        {
            name="loyalty-counter";pickingMode=PickingMode.Ignore;style.position=Position.Absolute;
            number.style.position=Position.Absolute;number.style.left=number.style.top=0;
            number.style.width=Length.Percent(100);number.style.height=Length.Percent(78);
            number.style.marginLeft=number.style.marginRight=number.style.marginTop=number.style.marginBottom=0;
            number.style.paddingLeft=number.style.paddingRight=number.style.paddingTop=number.style.paddingBottom=0;
            number.style.unityTextAlign=TextAnchor.MiddleCenter;number.style.color=Color.white;number.style.unityFontStyleAndWeight=FontStyle.Bold;Add(number);
            generateVisualContent+=context=>{
                var p=context.painter2D;p.fillColor=new Color(.035f,.035f,.032f);p.strokeColor=new Color(.85f,.86f,.79f);p.lineWidth=Mathf.Max(1,contentRect.width*.035f);
                var size=contentRect.size-Vector2.one*2;
                p.BeginPath();p.MoveTo(Vector2.one+Vector2.Scale(Outline[0],size));
                for(int i=1;i<Outline.Length;i++)p.LineTo(Vector2.one+Vector2.Scale(Outline[i],size));
                p.ClosePath();p.Fill();p.Stroke();
            };
        }
        public void SetValue(string value){number.text=value??"";number.style.display=string.IsNullOrEmpty(value)?DisplayStyle.None:DisplayStyle.Flex;}
        public void Resize(float size){number.style.fontSize=size;CardTypography.Apply(number,CardTextRole.PowerToughness);}
    }
}
