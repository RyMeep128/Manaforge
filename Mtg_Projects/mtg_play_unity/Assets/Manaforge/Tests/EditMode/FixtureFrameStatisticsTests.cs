using System;
using NUnit.Framework;

namespace Manaforge.Play.Tests
{
    public sealed class FixtureFrameStatisticsTests
    {
        [Test]
        public void UsesNearestRankAndPreservesInputOrder()
        {
            var values = new double[] { 100, 1, 10, 2 };
            var result = FixtureFrameStatistics.Summarize(values);
            Assert.That(result.sampleCount, Is.EqualTo(4));
            Assert.That(result.meanMs, Is.EqualTo(28.25));
            Assert.That(result.medianMs, Is.EqualTo(2));
            Assert.That(result.p95Ms, Is.EqualTo(100));
            Assert.That(result.p99Ms, Is.EqualTo(100));
            Assert.That(result.maximumMs, Is.EqualTo(100));
            Assert.That(values[0], Is.EqualTo(100));
        }
        [TestCase(0)]
        [TestCase(-1)]
        [TestCase(double.NaN)]
        [TestCase(double.PositiveInfinity)]
        public void RejectsInvalidIntervals(double value) =>
            Assert.Throws<ArgumentException>(() => FixtureFrameStatistics.Summarize(new[] { value }));
        [Test]
        public void RejectsEmptySamples() => Assert.Throws<ArgumentException>(() => FixtureFrameStatistics.Summarize(Array.Empty<double>()));
    }
}
