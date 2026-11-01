using NUnit.Framework;
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
        [Test] public void ExtraActionsPreventRelabeling()
        {var root=Panel();root.Add(new Button());Assert.That(OpeningMulliganControls.Apply(root,7),Is.False);}
    }
}
