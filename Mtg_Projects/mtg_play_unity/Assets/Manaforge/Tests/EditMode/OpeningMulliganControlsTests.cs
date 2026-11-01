using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningMulliganControlsTests
    {
        private static VisualElement Panel(string question="Mulligan down to 6 cards?",string yes="Yes",string no="No")
        {
            var root=new VisualElement();root.Add(new Label(question){name="decision-prompt"});
            root.Add(new Button(){name="decision-option-0",text=yes});root.Add(new Button(){name="decision-option-1",text=no});return root;
        }
        [Test] public void LabelsPreserveButtonIdentityAndDisabledState()
        {
            var root=Panel();var yes=root.Q<Button>("decision-option-0");var no=root.Q<Button>("decision-option-1");
            no.SetEnabled(false);
            Assert.That(OpeningMulliganControls.Apply(root,7),Is.True);
            Assert.That(root.Q<Button>("decision-option-0"),Is.SameAs(yes));Assert.That(yes.text,Is.EqualTo("Mulligan"));Assert.That(no.text,Is.EqualTo("Keep 7"));Assert.That(no.enabledSelf,Is.False);
        }
        [TestCase("Another decision","Yes","No",7)]
        [TestCase("Mulligan down to 6 cards?","No","Yes",7)]
        [TestCase("Mulligan down to 6 cards?","Yes","No",6)]
        public void UnrecognizedDecisionsKeepEngineLabels(string prompt,string yes,string no,int count)
        {var root=Panel(prompt,yes,no);Assert.That(OpeningMulliganControls.Apply(root,count),Is.False);Assert.That(root.Q<Button>("decision-option-0").text,Is.EqualTo(yes));Assert.That(root.Q<Button>("decision-option-1").text,Is.EqualTo(no));}
        [Test] public void MissingTextureRetainsFallbackForBothButtons()
        {var root=Panel();OpeningMulliganControls.Apply(root,7);Assert.That(OpeningMulliganControls.ApplySkins(root,null,null),Is.False);Assert.That(root.Q<Button>("decision-option-0").style.backgroundImage.value.texture,Is.Null);}
        [Test] public void SuppliedTexturesPreserveButtonsAndDisabledState()
        {
            var texture=new Texture2D(2,2);try{
                var root=Panel();OpeningMulliganControls.Apply(root,7);var keep=root.Q<Button>("decision-option-1");keep.SetEnabled(false);
                Assert.That(OpeningMulliganControls.ApplySkins(root,texture,texture),Is.True);Assert.That(keep.style.backgroundImage.value.texture,Is.SameAs(texture));Assert.That(keep.enabledSelf,Is.False);Assert.That(keep.text,Is.EqualTo("Keep 7"));
            }finally{Object.DestroyImmediate(texture);}
        }
        [Test] public void ExtraActionsPreventRelabeling()
        {var root=Panel();root.Add(new Button());Assert.That(OpeningMulliganControls.Apply(root,7),Is.False);}
    }
}
