using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Reuses the UI Toolkit Painter2D approach used by BattlefieldLinks. No downloaded
    // textures, shaders, cameras or additional render pipeline are required.
    public sealed class ForgeMotionVisual : VisualElement
    {
        public Vector2 Center,Target;
        public Color Tint=new Color(1,.43f,.12f);
        public float Progress,Radius=55;
        public int ParticleCount;
        public bool Reduced,Link,Runes=true;
        public ForgeMotionVisual()
        {
            name="forge-motion-visual";pickingMode=PickingMode.Ignore;
            style.position=Position.Absolute;style.left=style.right=style.top=style.bottom=0;
            generateVisualContent+=Paint;
        }
        private void Paint(MeshGenerationContext context)
        {
            float t=Mathf.Clamp01(Progress),fade=Reduced?1-t:Mathf.Sin(Mathf.PI*t);
            if(fade<=0)return;
            var p=context.painter2D;var tint=Tint;tint.a=fade*.85f;p.strokeColor=tint;
            float radius=Radius*(Reduced?1:.7f+.6f*t);p.lineWidth=Reduced?2:2.5f;
            Ring(radius,48,0);if(!Reduced && Runes)Ring(radius*.83f,6,t*45);
            if(!Reduced && Runes)for(int i=0;i<6;i++){
                float angle=(i*60+t*45)*Mathf.Deg2Rad;var direction=new Vector2(Mathf.Cos(angle),Mathf.Sin(angle));
                var side=new Vector2(-direction.y,direction.x);var point=Center+direction*radius;
                p.BeginPath();p.MoveTo(point+direction*9);p.LineTo(point+side*4);p.LineTo(point-direction*9);p.LineTo(point-side*4);p.ClosePath();p.Stroke();
            }
            if(Link && !Reduced){
                p.lineWidth=4;p.BeginPath();p.MoveTo(Center);p.LineTo(Vector2.Lerp(Center,Target,Mathf.SmoothStep(0,1,Mathf.Min(1,t*2))));p.Stroke();
            }
            if(!Reduced)for(int i=0;i<ParticleCount;i++){
                float angle=(i*137.508f+t*22)*Mathf.Deg2Rad;var direction=new Vector2(Mathf.Cos(angle),Mathf.Sin(angle));
                float distance=radius*(.35f+t*(1.1f+(i%3)*.3f));var point=Center+direction*distance+new Vector2(0,-t*t*28);
                var ember=tint;ember.a*=1-t*.5f;p.strokeColor=ember;p.lineWidth=2+(i%3);
                p.BeginPath();p.MoveTo(point);p.LineTo(point-direction*(4+(i%4)*2));p.Stroke();
            }
            void Ring(float size,int segments,float rotation){
                p.BeginPath();for(int i=0;i<=segments;i++){
                    float angle=(i*360f/segments+rotation)*Mathf.Deg2Rad;var point=Center+new Vector2(Mathf.Cos(angle),Mathf.Sin(angle))*size;
                    if(i==0)p.MoveTo(point);else p.LineTo(point);
                }p.ClosePath();p.Stroke();
            }
        }
    }
}
