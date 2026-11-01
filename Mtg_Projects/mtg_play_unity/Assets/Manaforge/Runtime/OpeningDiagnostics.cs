using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public static class OpeningDiagnostics
    {
        // Preserve live status and inspection controls without placing them over the hand by default.
        public static Foldout Attach(VisualElement root,Label status,Label note,VisualElement inspection)
        {
            var details=new Foldout{name="opening-diagnostics",text="Connection details / inspect",value=false};
            details.style.position=Position.Absolute;details.style.left=8;details.style.top=8;details.style.width=390;
            details.style.color=Color.white;details.style.backgroundColor=new Color(.025f,.035f,.05f,.94f);
            details.style.paddingLeft=8;details.style.paddingRight=8;details.style.paddingTop=4;details.style.paddingBottom=4;
            status.style.whiteSpace=WhiteSpace.Normal;note.style.whiteSpace=WhiteSpace.Normal;
            inspection.style.flexWrap=Wrap.Wrap;details.Add(status);details.Add(note);details.Add(inspection);root.Add(details);return details;
        }
    }
}
