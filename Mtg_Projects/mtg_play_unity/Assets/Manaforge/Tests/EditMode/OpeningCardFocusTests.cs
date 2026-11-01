using NUnit.Framework;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningCardFocusTests
    {
        [UnityEngine.TestTools.UnityTest] public System.Collections.IEnumerator ResizePreservesOriginalFanPositionsWhileCardIsRaised()
        {
            if(UnityEngine.SystemInfo.graphicsDeviceType==UnityEngine.Rendering.GraphicsDeviceType.Null)Assert.Ignore("Mounted layout requires a graphics device.");
            var window=UnityEngine.ScriptableObject.CreateInstance<UnityEditor.EditorWindow>();
            var a=new CardView();var b=new CardView();
            try{
                window.Show();var root=window.rootVisualElement;root.style.width=800;root.Add(a);root.Add(b);
                using(var focus=new OpeningCardFocus(root)){
                    yield return null;focus.PresentHand();focus.Show(a);
                    root.style.width=1000;yield return null;focus.PresentHand();
                    var expected=OpeningHandFan.Arrange(2,root.resolvedStyle.width);
                    Assert.That(a.style.left.value.value,Is.EqualTo(expected[0].Left).Within(.01f));
                    Assert.That(b.style.left.value.value,Is.EqualTo(expected[1].Left).Within(.01f));
                    Assert.That(root[1],Is.SameAs(a));Assert.That(a.style.scale.value.value.x,Is.EqualTo(1.12f));
                    focus.Show(null);Assert.That(root[0],Is.SameAs(a));
                }
            }finally{a.Dispose();b.Dispose();window.Close();}
        }
        [Test] public void RaisingCardsPreservesTabOrderAndDisposalRestoresOriginalSettings()
        {
            var root=new VisualElement();var a=new CardView{tabIndex=7,focusable=true};var b=new CardView{tabIndex=-1};root.Add(a);root.Add(b);
            using(var focus=new OpeningCardFocus(root)){
                focus.Show(a);Assert.That(root[1],Is.SameAs(a));
                Assert.That(a.tabIndex,Is.EqualTo(1));Assert.That(b.tabIndex,Is.EqualTo(2));
                Assert.That(a.focusable,Is.True);Assert.That(b.focusable,Is.True);
            }
            Assert.That(a.tabIndex,Is.EqualTo(7));Assert.That(b.tabIndex,Is.EqualTo(-1));
            Assert.That(a.focusable,Is.True);Assert.That(b.focusable,Is.False);
            a.Dispose();b.Dispose();
        }
        [Test] public void PointerLeavingRestoresKeyboardFocusedCard()
        {
            if(UnityEngine.SystemInfo.graphicsDeviceType==UnityEngine.Rendering.GraphicsDeviceType.Null)Assert.Ignore("Mounted focus events require a graphics device.");
            var window=UnityEngine.ScriptableObject.CreateInstance<UnityEditor.EditorWindow>();
            try{
            window.Show();var root=window.rootVisualElement;var a=new CardView();var b=new CardView();root.Add(a);root.Add(b);
            using(var focus=new OpeningCardFocus(root)){
                a.Focus();
                using(var ev=PointerEnterEvent.GetPooled()){ev.target=b;b.SendEvent(ev);}
                Assert.That(b.style.scale.value.value.x,Is.EqualTo(1.12f));
                using(var ev=PointerLeaveEvent.GetPooled()){ev.target=b;b.SendEvent(ev);}
                Assert.That(a.style.scale.value.value.x,Is.EqualTo(1.12f));
                Assert.That(b.style.scale.value.value.x,Is.EqualTo(1));
                a.Blur();
                Assert.That(a.style.scale.value.value.x,Is.EqualTo(1));
            }
            a.Dispose();b.Dispose();
            }finally{window.Close();}
        }
        [Test] public void FocusRaisesOnlyTheChosenCardAndRestoresFanOrder()
        {
            var root=new VisualElement();var a=new CardView();var b=new CardView();root.Add(a);root.Add(b);
            using(var focus=new OpeningCardFocus(root)){
                focus.Show(a);Assert.That(root[1],Is.SameAs(a));Assert.That(a.style.scale.value.value.x,Is.EqualTo(1.12f));
                focus.Show(b);Assert.That(a.style.scale.value.value.x,Is.EqualTo(1));Assert.That(root[1],Is.SameAs(b));
                focus.Show(null);Assert.That(root[0],Is.SameAs(a));Assert.That(b.style.scale.value.value.x,Is.EqualTo(1));
            }
            Assert.That(a.focusable,Is.False);a.Dispose();b.Dispose();
        }
        [TestCase("Basic Land", "0", "0", null)]
        [TestCase("Artifact Creature", "0", "2", "0/2")]
        [TestCase("Creature", "*", "*", "*/*")]
        [TestCase("Artifact", "0", "0", null)]
        [TestCase(null, "0", "0", null)]
        public void NoncreatureGatewayDefaultsDoNotBecomeVisibleStats(string type,string power,string toughness,string expected)
        {Assert.That(ViewerCardSurface.DisplayPowerToughness(type,power,toughness),Is.EqualTo(expected));}
        [Test] public void ForeignOrClearedCardsCannotBeRaised()
        {
            var root=new VisualElement();var card=new CardView();root.Add(card);var foreign=new CardView();
            var focus=new OpeningCardFocus(root);focus.Show(foreign);Assert.That(root.childCount,Is.EqualTo(1));root.Clear();focus.Show(card);Assert.That(root.childCount,Is.Zero);focus.Dispose();focus.Show(card);Assert.That(root.childCount,Is.Zero);card.Dispose();foreign.Dispose();
        }
    }
}
