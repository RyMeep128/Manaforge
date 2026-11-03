using System;
using System.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class SeatLayoutTests
    {
        [TestCase(2)]
        [TestCase(3)]
        [TestCase(4)]
        [TestCase(5)]
        [TestCase(6)]
        public void SeatsHaveDistinctPositionsWithoutAFiveSeatMaximum(int count)
        {
            var positions = Enumerable.Range(0, count).Select(seat => SeatLayout.Position(seat, count)).ToArray();
            Assert.That(positions.Distinct().Count(), Is.EqualTo(count));
            Assert.That(positions[0].y, Is.LessThan(0), "Local seat stays below the table");
        }

        [Test]
        public void InvalidSeatCannotProduceAnUnownedLayout()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => SeatLayout.Position(-1, 2));
            Assert.Throws<ArgumentOutOfRangeException>(() => SeatLayout.Position(2, 2));
            Assert.Throws<ArgumentOutOfRangeException>(() => SeatLayout.Position(0, 1));
        }
    }
}
