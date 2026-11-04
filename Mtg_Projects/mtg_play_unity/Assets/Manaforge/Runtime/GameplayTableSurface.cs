using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Decorative, original table material. Geometry comes from the composition.
    public sealed class GameplayTableSurface : VisualElement
    {
        public GameplayTableSurface()
        {
            pickingMode=PickingMode.Ignore;AddToClassList("mf-table-surface");
            var seam=new VisualElement{pickingMode=PickingMode.Ignore};seam.AddToClassList("mf-table-seam");Add(seam);
        }
    }
}
