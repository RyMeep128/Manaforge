using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Opt-in public-card renderer demonstration. No decisions or gameplay commands.
    public sealed class ArtworkFixtureScene : MonoBehaviour
    {
        private readonly CancellationTokenSource cancellation = new CancellationTokenSource();
        private readonly List<CardView> views = new List<CardView>();
        private FixtureTextures textures;
        private PanelSettings settings;
        private UIDocument document;
        private CardView preview;
        private ArtworkFixture fixture;
        private Label message;
        private VisualElement board;
        public int ObjectCount { get; private set; }
        public bool Ready { get; private set; }
        public static string Argument(string name)
        {
            var args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        }
        private IEnumerator Start()
        {
            settings = ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet = Resources.Load<ThemeStyleSheet>("CardTheme");
            settings.scaleMode = PanelScaleMode.ScaleWithScreenSize;
            settings.referenceResolution = new Vector2Int(1280, 720);
            document = gameObject.AddComponent<UIDocument>();
            document.panelSettings = settings;
            var root = document.rootVisualElement;
            root.style.flexGrow = 1;
            root.style.backgroundColor = new Color(0.025f, 0.055f, 0.075f);
            var title = new Label("MANAFORGE / PUBLIC ARTWORK FIXTURE");
            title.style.fontSize = 24; title.style.color = Color.white; title.style.marginLeft = 24; title.style.marginTop = 18;
            root.Add(title);
            message = new Label("Loading verified local artwork…");
            message.style.color = Color.white; message.style.marginLeft = 24; root.Add(message);
            var controls = new VisualElement(); controls.style.flexDirection = FlexDirection.Row; root.Add(controls);
            foreach (int count in new[] { 20, 70, 200 })
            { int captured = count; controls.Add(new Button(() => Populate(captured)) { text = count + " objects" }); }
            board = new VisualElement();
            board.style.position = Position.Absolute; board.style.left = 24; board.style.top = 125;
            board.style.width = 900; board.style.height = 560;
            root.Add(board);
            preview = new CardView(); preview.style.position = Position.Absolute;
            preview.style.left = 952; preview.style.top = 160; root.Add(preview);
            var loading = ArtworkFixture.LoadAsync(Argument("-manaforgeArtworkFixture"), cancellation.Token);
            while (!loading.IsCompleted) yield return null;
            if (loading.IsFaulted || loading.IsCanceled)
            { message.text = "Fixture failed validation. No artwork displayed.";
                if (Argument("-manaforgeArtworkOutput") != null) Application.Quit(1);
                yield break; }
            fixture = loading.Result;
            textures = new FixtureTextures();
            foreach (var card in fixture.Cards)
            { textures.Get(card.Artwork); yield return null; } // at most one upload per frame
            int initial = 20;
            if (int.TryParse(Argument("-manaforgeFixtureCount"), out int countArg)
                && (countArg == 20 || countArg == 70 || countArg == 200)) initial = countArg;
            Populate(initial); Ready = true;
            string output = Argument("-manaforgeArtworkOutput");
            if (output != null) yield return Capture(output);
        }
        private void Populate(int count)
        {
            if (fixture == null || textures == null) return;
            foreach (var view in views) view.Dispose(); views.Clear();
            preview.Conceal();
            int columns = count == 20 ? 5 : count == 70 ? 10 : 20;
            int rows = (count + columns - 1) / columns;
            float width = Mathf.Min(160, Mathf.Min(880f / columns - 5, 535f / rows / 0.78f - 5));
            for (int i = 0; i < count; i++)
            {
                var card = fixture.Cards[i % fixture.Cards.Count];
                var view = new CardView();
                view.Bind(card.Identity, textures.Get(card.Artwork), new Rect(0.08f, 0.45f, 0.84f, 0.38f));
                view.UpdateValues(card.MockValues); view.SetPresentation(CardPresentationMode.Compact, width);
                view.style.position = Position.Absolute;
                view.style.left = (i % columns) * (width + 5); view.style.top = (i / columns) * (width * 0.78f + 5);
                view.RegisterCallback<PointerEnterEvent>(_ => Show(card));
                view.RegisterCallback<PointerDownEvent>(_ => {
                    foreach (var other in views) other.style.borderTopWidth = 0;
                    view.style.borderTopColor = Color.cyan; view.style.borderTopWidth = 3; Show(card);
                });
                board.Add(view); views.Add(view);
            }
            ObjectCount = count;
            message.text = $"{count} display objects · {textures.Count} shared textures · PRINTED MOCK values · Hover to inspect / click to select · No live game";
            Show(fixture.Cards[0]);
        }
        private void Show(ArtworkFixture.Card card)
        {
            preview.Bind(card.Identity, textures.Get(card.Artwork), new Rect(0.08f, 0.45f, 0.84f, 0.38f));
            preview.SetPresentation(CardPresentationMode.Full, 285); preview.UpdateValues(card.MockValues);
        }
        private IEnumerator Capture(string output)
        {
            // UI Toolkit renders into its own target; camera-only capture omits the panel.
            var target = new RenderTexture(1280, 720, 0);
            target.Create(); settings.targetTexture = target;
            for (int i = 0; i < 30; i++) yield return null;
            var image = new Texture2D(1280, 720, TextureFormat.RGBA32, false);
            var previous = RenderTexture.active;
            try
            {
                RenderTexture.active = target; image.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0); image.Apply();
                Directory.CreateDirectory(output);
                File.WriteAllBytes(Path.Combine(output, "artwork-" + ObjectCount + ".png"), image.EncodeToPNG());
                File.WriteAllText(Path.Combine(output, "artwork-" + ObjectCount + ".json"),
                    JsonUtility.ToJson(new CaptureReport { fixtureOnly = true, objectCount = ObjectCount,
                        textureCount = textures.Count, textureBytes = textures.Bytes,
                        graphicsDevice = SystemInfo.graphicsDeviceName, editorVersion = Application.unityVersion }, true));
            }
            finally
            {
                RenderTexture.active = previous; settings.targetTexture = null;
                target.Release(); Destroy(target); Destroy(image);
            }
            Application.Quit(0);
        }
        private void OnDestroy()
        {
            cancellation.Cancel(); cancellation.Dispose();
            foreach (var view in views) view.Dispose(); views.Clear(); preview?.Dispose();
            textures?.Dispose();
            if (document != null) document.rootVisualElement.Clear();
            if (settings != null) Destroy(settings);
        }
        [Serializable] private sealed class CaptureReport
        {
            public bool fixtureOnly;
            public int objectCount, textureCount;
            public long textureBytes;
            public string graphicsDevice, editorVersion;
        }
    }
}
