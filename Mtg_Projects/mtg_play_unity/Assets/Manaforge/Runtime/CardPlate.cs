using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Beveled inset for independently supplied names/stats; the printing supplies the outer frame.
    public sealed class CardPlate : VisualElement
    {
        public CardPlate(string plateName)
        {
            name=plateName;pickingMode=PickingMode.Ignore;style.position=Position.Absolute;
            generateVisualContent += context => {
                var p=context.painter2D;float w=contentRect.width,h=contentRect.height;
                if(w<=0 || h<=0)return;
                float bevel=Mathf.Min(1,h/16f);
                Draw(p,w,h,0,new Color(.09f,.10f,.09f));
                Draw(p,w,h,bevel,new Color(.62f,.64f,.59f));
                Draw(p,w,h,2*bevel,new Color(.23f,.25f,.23f));
                Draw(p,w,h,3*bevel,new Color(.86f,.87f,.81f));
            };
        }
        private static void Draw(Painter2D p,float width,float height,float inset,Color color)
        {
            float cut=Mathf.Min(height*.20f,width*.08f),right=width-inset,bottom=height-inset;
            p.fillColor=color;p.BeginPath();p.MoveTo(new Vector2(inset+cut,inset));p.LineTo(new Vector2(right-cut,inset));
            p.LineTo(new Vector2(right,inset+cut));p.LineTo(new Vector2(right,bottom-cut));p.LineTo(new Vector2(right-cut,bottom));
            p.LineTo(new Vector2(inset+cut,bottom));p.LineTo(new Vector2(inset,bottom-cut));p.LineTo(new Vector2(inset,inset+cut));p.ClosePath();p.Fill();
        }
    }
}
