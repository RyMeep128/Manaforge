using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Screen geometry only; callers supply links from already-projected assignments.
    public sealed class BattlefieldLinks : VisualElement
    {
        public readonly struct Link
        {
            public readonly Vector2 From,To;public readonly Color Color;
            public Link(Vector2 from,Vector2 to,Color color){From=from;To=to;Color=color;}
        }
        public float LineWidth {get;set;}=2.5f;
        private readonly List<Link> links=new List<Link>();
        public BattlefieldLinks(){name="battlefield-links";pickingMode=PickingMode.Ignore;generateVisualContent+=Draw;}
        public void Set(IEnumerable<Link> next){links.Clear();links.AddRange(next);MarkDirtyRepaint();}
        private void Draw(MeshGenerationContext context)
        {
            var painter=context.painter2D;painter.lineWidth=LineWidth;
            foreach(var link in links){
                if(Vector2.Distance(link.From,link.To)<1)continue;var direction=(link.To-link.From).normalized;var side=new Vector2(-direction.y,direction.x);
                painter.strokeColor=link.Color;painter.BeginPath();painter.MoveTo(link.From);var tangent=new Vector2(0,Mathf.Sign(link.To.y-link.From.y)*Mathf.Min(75,Mathf.Abs(link.To.y-link.From.y)*.4f));painter.BezierCurveTo(link.From+tangent,link.To-tangent,link.To);painter.Stroke();
                if(tangent.sqrMagnitude>1){direction=tangent.normalized;side=new Vector2(-direction.y,direction.x);}
                painter.BeginPath();painter.MoveTo(link.To-direction*13+side*6);painter.LineTo(link.To);painter.LineTo(link.To-direction*13-side*6);painter.Stroke();
            }
        }
    }
}
