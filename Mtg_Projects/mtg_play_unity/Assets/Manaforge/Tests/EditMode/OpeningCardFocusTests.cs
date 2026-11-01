using NUnit.Framework;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningCardFocusTests
    {
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
