using NUnit.Framework;
namespace Manaforge.Play.Tests
{
    public sealed class ArenaLibraryMotionTests
    {
        [TestCase(50,49,6,7,1)]
        [TestCase(50,47,6,9,3)]
        [TestCase(50,49,6,6,0)]
        [TestCase(50,50,6,7,0)]
        [TestCase(50,51,6,7,0)]
        [TestCase(50,40,6,16,6)]
        public void MovementRequiresConfirmedChangesOnBothSides(long beforeLibrary,long afterLibrary,long beforeHand,long afterHand,int expected)
        {Assert.That(ArenaLibraryMotion.ConfirmedHandArrivals(beforeLibrary,afterLibrary,beforeHand,afterHand),Is.EqualTo(expected));}
        [Test] public void UnknownCountsDoNotInventMovement()
        {Assert.That(ArenaLibraryMotion.ConfirmedHandArrivals(null,49,6,7),Is.Zero);Assert.That(ArenaLibraryMotion.ConfirmedHandArrivals(50,49,null,7),Is.Zero);}
    }
}
