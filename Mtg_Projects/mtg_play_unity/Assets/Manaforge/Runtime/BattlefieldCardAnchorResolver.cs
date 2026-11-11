using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Reads final borrowed-view geometry; no competing card position or identity store.
    public static class BattlefieldCardAnchorResolver
    {
        public static bool TryCenter(VisualElement destination,CardView view,out Vector2 center)
        {
            center=default;if(destination==null || view?.parent==null || view.worldBound.width<=1 || view.worldBound.height<=1)return false;
            for(var element=(VisualElement)view;element!=null;element=element.parent)if(element.resolvedStyle.display==DisplayStyle.None || element.resolvedStyle.visibility==Visibility.Hidden)return false;
            center=destination.WorldToLocal(view.worldBound.center);return !float.IsNaN(center.x) && !float.IsNaN(center.y) && !float.IsInfinity(center.x) && !float.IsInfinity(center.y);
        }
    }
}
