using System;
using System.Collections;
using System.IO;
using Manaforge.Play;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class MatchRecoveryOverlayTests
    {
        private static void Click(VisualElement root,string name){var button=root.Q<Button>(name);using(var input=NavigationSubmitEvent.GetPooled()){input.target=button;button.SendEvent(input);}}
        [UnityTest] public IEnumerator ViewingTheBattlefieldDoesNotResumeAndEndingRequiresConfirmation()
        {
            string directory=Path.Combine(Path.GetTempPath(),"manaforge-recovery-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(directory);
            File.WriteAllText(Path.Combine(directory,"recovery-role.json"),"{\"host\":true}");
            File.WriteAllText(Path.Combine(directory,"recovery-state.json"),"{\"paused\":true,\"connected\":false,\"controller\":\"human\",\"can_resume\":false}");
            var node=new GameObject("Recovery overlay test");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            var overlay=new MatchRecoveryOverlay(document.rootVisualElement,directory);
            try{
                yield return null;overlay.Tick();Assert.That(overlay.Paused,Is.True);Assert.That(document.rootVisualElement.Q<Button>("recovery-resume").enabledSelf,Is.False);
                Click(document.rootVisualElement,"recovery-view-battlefield");Assert.That(overlay.Paused,Is.True);Assert.That(document.rootVisualElement.Q("match-recovery-overlay").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(File.Exists(Path.Combine(directory,"recovery-action.json")),Is.False);
                Click(document.rootVisualElement,"recovery-reopen");Click(document.rootVisualElement,"recovery-end-game");Assert.That(File.Exists(Path.Combine(directory,"recovery-action.json")),Is.False);
                Click(document.rootVisualElement,"recovery-cancel-end");Click(document.rootVisualElement,"recovery-add-ai");
                Assert.That((string)JObject.Parse(File.ReadAllText(Path.Combine(directory,"recovery-action.json")))["action"],Is.EqualTo("add_ai"));Assert.That(overlay.Paused,Is.True);
            }finally{overlay.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);Directory.Delete(directory,true);}
        }
    }
}
