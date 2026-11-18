using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Reads final borrowed-view geometry; no competing card position or identity store.
    public static class BattlefieldCardAnchorResolver
    {
        public static bool TryResolve(VisualElement destination,CardView view,VisualElement fallback,out Vector2 center)
        {
            if(TryCenter(destination,view,out center))return true;
            center=default;if(destination==null || fallback?.panel==null || fallback.worldBound.width<=1 || fallback.worldBound.height<=1)return false;
            for(var element=fallback;element!=null;element=element.parent)if(element.style.display.value==DisplayStyle.None || element.resolvedStyle.display==DisplayStyle.None || element.resolvedStyle.visibility==Visibility.Hidden)return false;
            center=destination.WorldToLocal(fallback.worldBound.center);return !float.IsNaN(center.x) && !float.IsNaN(center.y) && !float.IsInfinity(center.x) && !float.IsInfinity(center.y);
        }
        public static bool TryCenter(VisualElement destination,CardView view,out Vector2 center)
        {
            center=default;if(destination==null || view?.parent==null || view.style.display.value==DisplayStyle.None || view.worldBound.width<=1 || view.worldBound.height<=1)return false;
            for(var element=(VisualElement)view;element!=null;element=element.parent)if(element.resolvedStyle.display==DisplayStyle.None || element.resolvedStyle.visibility==Visibility.Hidden)return false;
            var point=view.worldBound.center;
            for(var element=view.parent;element!=null;element=element.parent)if(element is ScrollView scroll){
                var clip=scroll.contentViewport.worldBound;if(!clip.Overlaps(view.worldBound))return false;
                point=new Vector2(Mathf.Clamp(point.x,clip.xMin,clip.xMax),Mathf.Clamp(point.y,clip.yMin,clip.yMax));
            }
            center=destination.WorldToLocal(point);return !float.IsNaN(center.x) && !float.IsNaN(center.y) && !float.IsInfinity(center.x) && !float.IsInfinity(center.y);
        }
    }
}
