using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace Manaforge.Play
{
    // Fixture-only rendering smoke. No engine, deck data, legal actions or private cards.
    public sealed class FoundationTable : MonoBehaviour
    {
        public const int CardCount = 20;
        public Material cardTemplate;
        private Material cardMaterial;

        private void Awake()
        {
            Application.targetFrameRate = 60;
            if (ArtworkFixtureScene.Argument("-manaforgeSessionFixture") != null)
            {
                enabled = false;
                gameObject.AddComponent<SessionFixtureScene>();
                return;
            }
            if (ArtworkFixtureScene.Argument("-manaforgeBootstrapDiagnostic") != null)
            {
                enabled = false;
                gameObject.AddComponent<BootstrapDiagnosticScene>();
                return;
            }
            if (ArtworkFixtureScene.Argument("-manaforgeArtworkFixture") != null)
            {
                enabled = false;
                gameObject.AddComponent<ArtworkFixtureScene>();
                return;
            }
            if (cardTemplate == null) throw new InvalidOperationException("Fixture material missing");
            cardMaterial = new Material(cardTemplate);
            cardMaterial.color = new Color(0.14f, 0.35f, 0.43f);
            for (int seat = 0; seat < 2; seat++)
            {
                var center = SeatLayout.Position(seat, 2);
                for (int index = 0; index < CardCount / 2; index++)
                {
                    var card = GameObject.CreatePrimitive(PrimitiveType.Quad);
                    card.name = $"Fixture seat {seat} card {index}";
                    card.transform.SetParent(transform, false);
                    card.transform.localPosition = center + new Vector3((index - 4.5f) * 1.05f, 0, 0);
                    card.transform.localScale = new Vector3(0.92f, 1.3f, 1);
                    card.GetComponent<Renderer>().sharedMaterial = cardMaterial;
                }
            }
        }

        private IEnumerator Start()
        {
            string output = Argument("-manaforgeSmokeOutput");
            if (output == null) yield break;
            Directory.CreateDirectory(output);
            // A real graphics device is required: -nographics cannot prove rendering.
            for (int frame = 0; frame < 60; frame++) yield return null;
            yield return new WaitForEndOfFrame();
            string screenshot = Path.Combine(output, "foundation.png");
            // Render explicitly: hidden Windows players may have no capturable swapchain.
            var target = new RenderTexture(1280, 720, 24);
            var pixels = new Texture2D(1280, 720, TextureFormat.RGB24, false);
            var previous = RenderTexture.active;
            int renderedCardPixels = 0;
            try
            {
                var camera = FindFirstObjectByType<Camera>();
                RenderPipeline.SubmitRenderRequest(camera,
                    new RenderPipeline.StandardRequest { destination = target });
                RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0);
                pixels.Apply();
                foreach (var pixel in pixels.GetPixels32())
                    if (pixel.g > 40 && pixel.b > 40) renderedCardPixels++;
                File.WriteAllBytes(screenshot, pixels.EncodeToPNG());
            }
            finally
            {
                RenderTexture.active = previous;
                target.Release();
                Destroy(target);
                Destroy(pixels);
            }
            bool passed = File.Exists(screenshot) && new FileInfo(screenshot).Length > 0
                && transform.childCount == CardCount && GraphicsSettings.currentRenderPipeline != null
                && SystemInfo.graphicsDeviceType != GraphicsDeviceType.Null && renderedCardPixels > 10000;
            var report = new SmokeReport
            {
                passed = passed, editorVersion = Application.unityVersion,
                cardCount = transform.childCount, graphicsDevice = SystemInfo.graphicsDeviceName,
                width = 1280, height = 720, renderedCardPixels = renderedCardPixels
            };
            File.WriteAllText(Path.Combine(output, "smoke.json"), JsonUtility.ToJson(report, true));
            Application.Quit(passed ? 0 : 1);
        }

        private static string Argument(string name)
        {
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        }

        private void OnGUI()
        {
            var heading = new GUIStyle(GUI.skin.label) { fontSize = 26 };
            GUI.Label(new Rect(30, 20, Screen.width - 60, 45), "MANAFORGE  /  PLAY FOUNDATION", heading);
            GUI.Label(new Rect(30, 65, Screen.width - 60, 30),
                "Fixture only • 20 placeholder cards • URP • No live game or artwork");
            GUI.Label(new Rect(30, Screen.height - 45, Screen.width - 60, 30),
                "Local seat below · Opponent above · Graphics and packaging feasibility");
        }

        private void OnDestroy()
        {
            if (cardMaterial != null) Destroy(cardMaterial);
        }

        [Serializable]
        private sealed class SmokeReport
        {
            public bool passed;
            public string editorVersion;
            public int cardCount;
            public string graphicsDevice;
            public int width;
            public int height;
            public int renderedCardPixels;
        }
    }
}
