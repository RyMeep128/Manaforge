using System;
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
        private Func<IEnumerable<Link>> source;
        internal IReadOnlyList<Link> CurrentLinks=>links;
        internal void SetSource(Func<IEnumerable<Link>> current){source=current;MarkDirtyRepaint();}
        internal static Vector2 OutsideEdge(Rect bounds,Vector2 from)
        {
            var offset=from-bounds.center;float extent=Mathf.Max(Mathf.Abs(offset.x)/Mathf.Max(1,bounds.width*.5f),Mathf.Abs(offset.y)/Mathf.Max(1,bounds.height*.5f));
            return extent<=1?bounds.center:bounds.center+offset/extent+offset.normalized*5;
        }
        public float LineWidth {get;set;}=2.5f;
        private readonly List<Link> links=new List<Link>();
        public BattlefieldLinks(){name="battlefield-links";pickingMode=PickingMode.Ignore;generateVisualContent+=Draw;}
        public void Set(IEnumerable<Link> next){source=null;links.Clear();links.AddRange(next);MarkDirtyRepaint();}
        private void Draw(MeshGenerationContext context)
        {
            if(source!=null){links.Clear();var current=source();if(current!=null)links.AddRange(current);}
            var painter=context.painter2D;painter.lineWidth=LineWidth;
            foreach(var link in links){
                if(Vector2.Distance(link.From,link.To)<1)continue;var direction=(link.To-link.From).normalized;var side=new Vector2(-direction.y,direction.x);
                painter.strokeColor=link.Color;painter.BeginPath();painter.MoveTo(link.From);var tangent=new Vector2(0,Mathf.Sign(link.To.y-link.From.y)*Mathf.Min(75,Mathf.Abs(link.To.y-link.From.y)*.4f));painter.BezierCurveTo(link.From+tangent,link.To-direction*Mathf.Min(75,Vector2.Distance(link.From,link.To)*.4f),link.To);painter.Stroke();
                painter.BeginPath();painter.MoveTo(link.To-direction*13+side*6);painter.LineTo(link.To);painter.LineTo(link.To-direction*13-side*6);painter.Stroke();
            }
        }
    }
}
