using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace Manaforge.Play.Tests
{
    public sealed class FoundationSceneTests
    {
        [UnityTest]
        public IEnumerator PreparedSceneCreatesTheExpectedFixtureInUrp()
        {
            yield return SceneManager.LoadSceneAsync("Foundation");
            var table = Object.FindFirstObjectByType<FoundationTable>();
            Assert.That(table, Is.Not.Null);
            Assert.That(table.transform.childCount, Is.EqualTo(FoundationTable.CardCount));
            Assert.That(GraphicsSettings.currentRenderPipeline, Is.Not.Null);
            Assert.That(Object.FindFirstObjectByType<Camera>().enabled, Is.True);
            foreach (Transform card in table.transform)
                Assert.That(card.GetComponent<Renderer>().sharedMaterial.shader.name,
                    Is.EqualTo("Universal Render Pipeline/Unlit"));
        }
    }
}
