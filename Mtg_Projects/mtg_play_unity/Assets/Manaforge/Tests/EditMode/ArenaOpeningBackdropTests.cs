using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ArenaOpeningBackdropTests
    {
        [Test] public void MissingResourceLeavesTheExistingSurfaceUsable()
        {var root=new VisualElement();var button=new Button();root.Add(button);Assert.That(ArenaOpeningBackdrop.Attach(root,null),Is.False);Assert.That(root.childCount,Is.EqualTo(1));Assert.That(root[0],Is.SameAs(button));}
        [Test] public void BackdropStaysBehindControlsAndCannotInterceptInput()
        {
            var texture=new Texture2D(2,2);try{
                var root=new VisualElement();var button=new Button();root.Add(button);
                Assert.That(ArenaOpeningBackdrop.Attach(root,texture),Is.True);var image=root.Q<Image>("arena-opening-backdrop");
                Assert.That(root[0],Is.SameAs(image));Assert.That(root[1],Is.SameAs(button));Assert.That(image.pickingMode,Is.EqualTo(PickingMode.Ignore));Assert.That(image.image,Is.SameAs(texture));
                Assert.That(ArenaOpeningBackdrop.Attach(root,texture),Is.True);Assert.That(root.childCount,Is.EqualTo(2));
                Assert.That(image.uv,Is.EqualTo(new Rect(0,0,1,1)));Assert.That(image.scaleMode,Is.EqualTo(ScaleMode.StretchToFill));Assert.That(ArenaOpeningBackdrop.ResourceName,Does.EndWith("ArenaTutorialBattlefield"));
            }finally{Object.DestroyImmediate(texture);}
        }
    }
}
