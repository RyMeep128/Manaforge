using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Planar outer contour from the owner-provided BattlefieldPart_Cardbase_Default mesh.
    // Source path ID 4091911210820854842. No source shader or gameplay code is imported.
    public sealed class BattlefieldFrame : VisualElement
    {
        public const float Aspect=.878f;
        private static readonly Vector2[] Outline={
            new Vector2(0,.9466f),new Vector2(.0016f,.9604f),new Vector2(.0063f,.9733f),new Vector2(.0137f,.9844f),
            new Vector2(.0234f,.9929f),new Vector2(.0347f,.9982f),new Vector2(.0468f,1),new Vector2(.9532f,1),
            new Vector2(.9653f,.9982f),new Vector2(.9766f,.9929f),new Vector2(.9863f,.9844f),new Vector2(.9937f,.9733f),
            new Vector2(.9984f,.9604f),new Vector2(1,.9466f),new Vector2(1,.0534f),new Vector2(.9984f,.0396f),
            new Vector2(.9937f,.0267f),new Vector2(.9863f,.0156f),new Vector2(.9766f,.0071f),new Vector2(.9653f,.0018f),
            new Vector2(.9532f,0),new Vector2(.0468f,0),new Vector2(.0347f,.0018f),new Vector2(.0234f,.0071f),
            new Vector2(.0137f,.0156f),new Vector2(.0063f,.0267f),new Vector2(.0016f,.0396f),new Vector2(0,.0534f)};
        public BattlefieldFrame()
        {
            name="mini-surround";pickingMode=PickingMode.Ignore;style.position=Position.Absolute;
            generateVisualContent+=context=>{
                var p=context.painter2D;p.fillColor=new Color(.025f,.027f,.025f);p.strokeColor=new Color(.13f,.14f,.13f);p.lineWidth=1;
                p.BeginPath();p.MoveTo(Vector2.Scale(Outline[0],contentRect.size));
                for(int i=1;i<Outline.Length;i++)p.LineTo(Vector2.Scale(Outline[i],contentRect.size));
                p.ClosePath();p.Fill();p.Stroke();
            };
        }
    }
}
