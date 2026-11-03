using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Renderer fixture gestures only. Never connected to protocol actions or game state.
    public sealed class FixtureInteractions : IDisposable
    {
        private readonly IReadOnlyList<CardView> cards;
        private readonly Action<int> inspect;
        private readonly List<EventCallback<PointerEnterEvent>> enter = new List<EventCallback<PointerEnterEvent>>();
        private readonly List<EventCallback<PointerDownEvent>> down = new List<EventCallback<PointerDownEvent>>();
        private readonly HashSet<int> tapped = new HashSet<int>();
        private readonly TargetLine line;
        private readonly IVisualElementScheduledItem animation;
        private float targetStarted;
        private bool disposed;
        public int SelectedIndex { get; private set; } = -1;
        public int TargetIndex { get; private set; } = -1;
        public int SelectionCount { get; private set; }
        public int TapCount { get; private set; }
        public int TargetCount { get; private set; }
        public FixtureInteractions(VisualElement board, IReadOnlyList<CardView> cards, Action<int> inspect)
        {
            this.cards = cards ?? throw new ArgumentNullException(nameof(cards));
            this.inspect = inspect ?? throw new ArgumentNullException(nameof(inspect));
            line = new TargetLine { pickingMode = PickingMode.Ignore };
            line.StretchToParentSize(); board.Add(line);
            for (int i = 0; i < cards.Count; i++)
            {
                int index = i;
                EventCallback<PointerEnterEvent> hover = _ => inspect(index);
                EventCallback<PointerDownEvent> click = e => { if (e.button == 0) Select(index); };
                enter.Add(hover); down.Add(click);
                cards[i].RegisterCallback(hover); cards[i].RegisterCallback(click);
            }
            animation = line.schedule.Execute(() => {
                if (SelectedIndex < 0 || TargetIndex < 0) return;
                line.From = line.WorldToLocal(cards[SelectedIndex].worldBound.center);
                line.To = line.WorldToLocal(cards[TargetIndex].worldBound.center);
                line.Progress = Mathf.Clamp01((Time.unscaledTime - targetStarted) / 0.3f);
                line.MarkDirtyRepaint();
            }).Every(16);
        }
        public bool IsTapped(int index) => tapped.Contains(index);
        public void Select(int index)
        {
            if (disposed) throw new ObjectDisposedException(nameof(FixtureInteractions));
            if (index < 0 || index >= cards.Count) throw new ArgumentOutOfRangeException(nameof(index));
            if (SelectedIndex >= 0) cards[SelectedIndex].SetSelected(false);
            SelectedIndex = index; TargetIndex = -1; line.Progress = 0;
            cards[index].SetSelected(true);
            SelectionCount++; inspect(index); line.MarkDirtyRepaint();
        }
        public void ToggleSelectedTap()
        {
            if (disposed) throw new ObjectDisposedException(nameof(FixtureInteractions));
            if (SelectedIndex < 0) return;
            if (!tapped.Add(SelectedIndex)) tapped.Remove(SelectedIndex);
            cards[SelectedIndex].style.rotate = new Rotate(new Angle(IsTapped(SelectedIndex) ? 90 : 0, AngleUnit.Degree));
            TapCount++;
        }
        public void TargetNext()
        {
            if (disposed) throw new ObjectDisposedException(nameof(FixtureInteractions));
            if (SelectedIndex < 0 || cards.Count < 2) return;
            TargetIndex = (SelectedIndex + 1) % cards.Count;
            targetStarted = Time.unscaledTime; TargetCount++;
        }
        public void Dispose()
        {
            if (disposed) return;
            disposed = true; animation.Pause(); line.RemoveFromHierarchy();
            for (int i = 0; i < cards.Count; i++)
            {
                cards[i].UnregisterCallback(enter[i]); cards[i].UnregisterCallback(down[i]);
                cards[i].style.rotate = new Rotate(new Angle(0)); cards[i].SetSelected(false);
            }
            tapped.Clear(); SelectedIndex = TargetIndex = -1;
        }
        private sealed class TargetLine : VisualElement
        {
            public Vector2 From, To;
            public float Progress;
            public TargetLine() { generateVisualContent += Draw; }
            private void Draw(MeshGenerationContext context)
            {
                if (Progress <= 0) return;
                var painter = context.painter2D;
                painter.strokeColor = new Color(0.1f, 0.95f, 1); painter.lineWidth = 3;
                painter.BeginPath(); painter.MoveTo(From); painter.LineTo(Vector2.Lerp(From, To, Progress)); painter.Stroke();
            }
        }
    }
}
