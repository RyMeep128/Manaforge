using System;
using System.Collections.Generic;
using System.Linq;

namespace Manaforge.Play
{
    public static class FixtureFrameStatistics
    {
        [Serializable] public sealed class Result
        {
            public int sampleCount;
            public double meanMs, medianMs, p95Ms, p99Ms, maximumMs;
        }
        // Nearest-rank percentiles over finite positive wall-clock frame intervals.
        public static Result Summarize(IReadOnlyList<double> milliseconds)
        {
            if (milliseconds == null || milliseconds.Count == 0) throw new ArgumentException("No frame samples");
            var sorted = milliseconds.ToArray();
            foreach (double value in sorted)
                if (double.IsNaN(value) || double.IsInfinity(value) || value <= 0) throw new ArgumentException("Invalid frame sample");
            Array.Sort(sorted);
            return new Result { sampleCount = sorted.Length, meanMs = sorted.Average(),
                medianMs = sorted[(int)Math.Ceiling(sorted.Length * 0.5) - 1],
                p95Ms = sorted[(int)Math.Ceiling(sorted.Length * 0.95) - 1],
                p99Ms = sorted[(int)Math.Ceiling(sorted.Length * 0.99) - 1], maximumMs = sorted[sorted.Length - 1] };
        }
    }
}
