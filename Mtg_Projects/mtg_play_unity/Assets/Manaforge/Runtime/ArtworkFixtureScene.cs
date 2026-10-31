using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using UnityEngine;
using UnityEngine.UIElements;
using UnityEngine.Profiling;

namespace Manaforge.Play
{
    // Opt-in public-card renderer demonstration. No decisions or gameplay commands.
    public sealed class ArtworkFixtureScene : MonoBehaviour
    {
        private readonly CancellationTokenSource cancellation = new CancellationTokenSource();
        private readonly List<CardView> views = new List<CardView>();
        private FixtureInteractions interactions;
        private double processToReadyMs;
        private double fixtureStart;
        private double workerLoadMs;
        private double uploadMs;
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
            fixtureStart = Time.realtimeSinceStartupAsDouble;
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
            controls.Add(new Button(() => interactions?.ToggleSelectedTap()) { text = "Mock tap / untap" });
            controls.Add(new Button(() => interactions?.TargetNext()) { text = "Mock target next" });
            board = new VisualElement();
            board.style.position = Position.Absolute; board.style.left = 24; board.style.top = 145;
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
            workerLoadMs = (Time.realtimeSinceStartupAsDouble - fixtureStart) * 1000;
            double uploadStarted = Time.realtimeSinceStartupAsDouble;
            fixture = loading.Result;
            textures = new FixtureTextures();
            foreach (var card in fixture.Cards)
            { textures.Get(card.Artwork); yield return null; } // at most one upload per frame
            uploadMs = (Time.realtimeSinceStartupAsDouble - uploadStarted) * 1000;
            var names = new List<string>();
            foreach(var card in fixture.Cards)names.Add(card.MockValues.Name ?? card.Identity.RenderedFace);
            var inspector = new DropdownField("Inspect",names,0);inspector.style.width=420;
            inspector.labelElement.style.color=Color.white;
            inspector.RegisterValueChangedCallback(_ => {
                if(inspector.index>=0 && inspector.index<fixture.Cards.Count)Show(fixture.Cards[inspector.index]);
            });
            controls.Add(inspector);
            int initial = 20;
            if (int.TryParse(Argument("-manaforgeFixtureCount"), out int countArg)
                && (countArg == 20 || countArg == 70 || countArg == 200)) initial = countArg;
            Populate(initial);
            yield return null; yield return null; // allow panel layout/render work to run
            using (var process = System.Diagnostics.Process.GetCurrentProcess())
                processToReadyMs = (DateTime.UtcNow - process.StartTime.ToUniversalTime()).TotalMilliseconds;
            Ready = true;
            string output = Argument("-manaforgeArtworkOutput");
            if (output != null) yield return Capture(output);
        }
        private void Populate(int count)
        {
            if (fixture == null || textures == null) return;
            interactions?.Dispose();
            foreach (var view in views) view.Dispose(); views.Clear();
            preview.Conceal();
            var permanents=new List<ArtworkFixture.Card>();
            foreach(var card in fixture.Cards)if(CardCompactProfile.IsFixturePermanent(card.MockValues.TypeLine))permanents.Add(card);
            if(permanents.Count==0){ObjectCount=0;message.text="No permanent examples in this fixture. Use Inspect for spells and auxiliary cards.";return;}
            int columns = count == 20 ? 5 : count == 70 ? 10 : 20;
            int rows = (count + columns - 1) / columns;
            float width = Mathf.Min(160, Mathf.Min(880f / columns - 5, 535f / rows / BattlefieldFrame.Aspect - 5));
            for (int i = 0; i < count; i++)
            {
                var card = permanents[i % permanents.Count];
                var view = new CardView();
                view.Bind(card.Identity, textures.Get(card.Artwork), new Rect(0.08f, 0.45f, 0.84f, 0.42f));
                view.UpdateValues(card.MockValues); view.SetPresentation(CardPresentationMode.Compact, width);
                view.style.position = Position.Absolute;
                view.style.left = (i % columns) * (width + 5); view.style.top = (i / columns) * (width * BattlefieldFrame.Aspect + 5);
                board.Add(view); views.Add(view);
            }
            interactions = new FixtureInteractions(board, views, index => Show(permanents[index % permanents.Count]));
            ObjectCount = count;
            message.text = $"{count} battlefield examples · {textures.Count} shared textures · PRINTED MOCK values · Hover / select · Mock tap / target · No live game";
            Show(fixture.Cards[0]);
        }
        private void Show(ArtworkFixture.Card card)
        {
            preview.Bind(card.Identity, textures.Get(card.Artwork), new Rect(0.08f, 0.45f, 0.84f, 0.42f));
            preview.SetPresentation(CardPresentationMode.Full, 285); preview.UpdateValues(card.MockValues);
        }
        private IEnumerator Capture(string output)
        {
            // UI Toolkit renders into its own target; camera-only capture omits the panel.
            // Rounded card clipping requires stencil, including in the offscreen review capture.
            var target = new RenderTexture(1280, 720, 24);
            target.Create(); settings.targetTexture = target;
            int oldVsync = QualitySettings.vSyncCount, oldTarget = Application.targetFrameRate;
            Texture2D image = null;
            var previous = RenderTexture.active;
            try
            {
                bool benchmark = Argument("-manaforgeArtworkBenchmark") == "1";
                if (benchmark) { QualitySettings.vSyncCount = 0; Application.targetFrameRate = -1; }
                for (int i = 0; i < 60; i++) yield return null;
                var samples = new List<double>();
                var gpuSamples = new List<double>();
                var cpuSamples = new List<double>();
                var latestTiming = new FrameTiming[1];
                ulong lastTiming = 0;
                double duration = 0;

                if (benchmark)
                {
                    double started = Time.realtimeSinceStartupAsDouble, previousFrame = started;
                    while (samples.Count < 100000 && (duration < 5 || samples.Count < 240))
                    {
                        if (samples.Count % 60 == 0)
                        {
                            int selected = (samples.Count / 60) % views.Count;
                            using (var click = PointerDownEvent.GetPooled(new Event { type = EventType.MouseDown, button = 0, mousePosition = views[selected].worldBound.center })) { click.target = views[selected]; views[selected].SendEvent(click); }
                            interactions.ToggleSelectedTap(); interactions.TargetNext();

                        }
                        FrameTimingManager.CaptureFrameTimings();
                        document.rootVisualElement.MarkDirtyRepaint();
                        yield return new WaitForEndOfFrame();
                        double now = Time.realtimeSinceStartupAsDouble;
                        samples.Add((now - previousFrame) * 1000); previousFrame = now; duration = now - started;
                        if (FrameTimingManager.GetLatestTimings(1, latestTiming) > 0 && latestTiming[0].frameStartTimestamp != lastTiming)
                        {
                            lastTiming = latestTiming[0].frameStartTimestamp;
                            if (latestTiming[0].gpuFrameTime > 0) gpuSamples.Add(latestTiming[0].gpuFrameTime);
                            if (latestTiming[0].cpuFrameTime > 0) cpuSamples.Add(latestTiming[0].cpuFrameTime);
                        }
                    }
                    // Repeatable screenshot shows a visible mock tap/target after measurement.
                    interactions.Select(0);
                    if (!interactions.IsTapped(0)) interactions.ToggleSelectedTap();
                    interactions.TargetNext();
                    yield return new WaitForSecondsRealtime(0.35f);
                }
                QualitySettings.vSyncCount = oldVsync; Application.targetFrameRate = oldTarget;
                long unityAllocated = Profiler.GetTotalAllocatedMemoryLong();
                long unityReserved = Profiler.GetTotalReservedMemoryLong();
                long managedBytes = GC.GetTotalMemory(false);
                image = new Texture2D(1280, 720, TextureFormat.RGBA32, false);
                RenderTexture.active = target; image.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0); image.Apply();
                Directory.CreateDirectory(output);
                File.WriteAllBytes(Path.Combine(output, "artwork-" + ObjectCount + ".png"), image.EncodeToPNG());
                File.WriteAllText(Path.Combine(output, "artwork-" + ObjectCount + ".json"),
                    JsonUtility.ToJson(new CaptureReport { fixtureOnly = true, objectCount = ObjectCount,
                        textureCount = textures.Count, textureBytes = textures.Bytes,
                        graphicsDevice = SystemInfo.graphicsDeviceName, editorVersion = Application.unityVersion,
                        graphicsApi = SystemInfo.graphicsDeviceVersion, processor = SystemInfo.processorType,
                        systemMemoryMiB = SystemInfo.systemMemorySize, developmentBuild = Debug.isDebugBuild,
                        capturedUtc = DateTime.UtcNow.ToString("O"),
                        reportVersion = 2, benchmark = benchmark, measurementComplete = benchmark && duration >= 5 && samples.Count >= 240,
                        processToReadyMs = processToReadyMs, fixtureSetupAndLoadMs = workerLoadMs, uploadWithFrameYieldsMs = uploadMs,
                        measurementSeconds = duration, intervalsMs = samples.ToArray(),
                        frames = benchmark ? FixtureFrameStatistics.Summarize(samples) : null,
                        gpuFrames = gpuSamples.Count > 0 ? FixtureFrameStatistics.Summarize(gpuSamples) : null,
                        cpuFrames = cpuSamples.Count > 0 ? FixtureFrameStatistics.Summarize(cpuSamples) : null,
                        gpuTimingAvailable = gpuSamples.Count > 0, gpuIntervalsMs = gpuSamples.ToArray(), cpuIntervalsMs = cpuSamples.ToArray(),
                        unityAllocatedBytes = unityAllocated, unityReservedBytes = unityReserved, managedHeapBytes = managedBytes,
                        selectionCount = interactions.SelectionCount, tapCount = interactions.TapCount, targetCount = interactions.TargetCount,
                        qualityLevel = QualitySettings.GetQualityLevel(), width = 1280, height = 720,
                        timingMethod = "uncapped wall-clock end-of-frame intervals; scripted fixture gestures; panel RenderTexture; loop intervals are not GPU or physical input timings; optional GPU/CPU counters use FrameTimingManager",
                        memoryMethod = "Unity/managed counters before screenshot; external owner samples process; excludes total GPU memory"
                    }, true));
            }
            finally
            {
                QualitySettings.vSyncCount = oldVsync; Application.targetFrameRate = oldTarget;
                RenderTexture.active = previous;
                if (settings != null) settings.targetTexture = null;
                target.Release(); Destroy(target); Destroy(image);
            }
            Application.Quit(0);
        }
        private void OnDestroy()
        {
            cancellation.Cancel(); cancellation.Dispose();
            interactions?.Dispose();
            foreach (var view in views) view.Dispose(); views.Clear(); preview?.Dispose();
            textures?.Dispose();
            if (document != null) document.rootVisualElement?.Clear();
            if (settings != null) Destroy(settings);
        }
        [Serializable] private sealed class CaptureReport
        {
            public string graphicsApi, processor, capturedUtc;
            public int systemMemoryMiB;
            public bool developmentBuild;
            public int reportVersion;
            public bool benchmark, measurementComplete;
            public double processToReadyMs, fixtureSetupAndLoadMs, uploadWithFrameYieldsMs, measurementSeconds;
            public double[] intervalsMs;
            public FixtureFrameStatistics.Result frames, gpuFrames, cpuFrames;
            public bool gpuTimingAvailable;
            public double[] gpuIntervalsMs, cpuIntervalsMs;
            public long unityAllocatedBytes, unityReservedBytes, managedHeapBytes;
            public int selectionCount, tapCount, targetCount, qualityLevel, width, height;
            public string timingMethod, memoryMethod;
            public bool fixtureOnly;
            public int objectCount, textureCount;
            public long textureBytes;
            public string graphicsDevice, editorVersion;
        }
    }
}
