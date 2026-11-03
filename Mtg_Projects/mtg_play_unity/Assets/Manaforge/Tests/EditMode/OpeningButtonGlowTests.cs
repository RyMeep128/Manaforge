using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningButtonGlowTests
    {
        [Test] public void GlowPreservesButtonsAndFollowsSubmissionAvailability()
        {
            var texture=new Texture2D(2,2);try{
                var root=new VisualElement();var button=new Button(){text="Mulligan"};root.Add(button);
                using(var glow=new OpeningButtonGlow(root,texture)){
                    Assert.That(glow.Count,Is.EqualTo(1));Assert.That(root.Q<Button>(),Is.SameAs(button));var image=root.Q<Image>();Assert.That(image.pickingMode,Is.EqualTo(PickingMode.Ignore));
                    root.SetEnabled(false);glow.Refresh();Assert.That(image.style.display.value,Is.EqualTo(DisplayStyle.None));root.SetEnabled(true);glow.Refresh();Assert.That(image.style.display.value,Is.EqualTo(DisplayStyle.Flex));
                }
                Assert.That(root[0],Is.SameAs(button));Assert.That(root.Q<Image>(),Is.Null);
            }finally{Object.DestroyImmediate(texture);}
        }
        [Test] public void MissingTextureLeavesExistingControlsUntouched()
        {var root=new VisualElement();var button=new Button(){text="Keep 7"};root.Add(button);using(var glow=new OpeningButtonGlow(root,null)){Assert.That(glow.Count,Is.Zero);Assert.That(root[0],Is.SameAs(button));}}
    }
}
