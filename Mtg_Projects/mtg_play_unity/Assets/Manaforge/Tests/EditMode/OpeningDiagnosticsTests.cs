using NUnit.Framework;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningDiagnosticsTests
    {
        [Test] public void DetailsStartCollapsedAndRetainLiveControls()
        {
            var root=new VisualElement();var status=new Label("Connected");var note=new Label("Limits");var inspect=new VisualElement();var button=new Button(){text="Inspect 1"};button.SetEnabled(false);inspect.Add(button);
            root.Add(status);root.Add(note);root.Add(inspect);
            var details=OpeningDiagnostics.Attach(root,status,note,inspect);
            Assert.That(details.value,Is.False);Assert.That(root.childCount,Is.EqualTo(1));Assert.That(details.contentContainer.Contains(status),Is.True);Assert.That(details.contentContainer.Contains(note),Is.True);Assert.That(inspect[0],Is.SameAs(button));Assert.That(button.enabledSelf,Is.False);
            details.value=true;status.text="Viewer cleared";Assert.That(status.text,Is.EqualTo("Viewer cleared"));Assert.That(details.contentContainer.Contains(inspect),Is.True);
        }
    }
}
