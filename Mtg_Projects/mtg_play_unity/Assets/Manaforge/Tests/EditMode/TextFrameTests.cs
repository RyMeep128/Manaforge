using System;
using System.IO;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class TextFrameTests
    {
        private sealed class Fragmented : MemoryStream
        {
            private readonly bool fragmented;
            public Fragmented(byte[] bytes, bool fragmented) : base(bytes) { this.fragmented = fragmented; }
            public override int Read(byte[] buffer, int offset, int count) => base.Read(buffer, offset, fragmented ? Math.Min(1, count) : count);
        }
        private static byte[] Hex(string value) => Enumerable.Range(0, value.Length / 2)
            .Select(i => Convert.ToByte(value.Substring(i * 2, 2), 16)).ToArray();

        [TestCase(false)] [TestCase(true)]
        public void SharedCorpusRoundTripsAndRejectsInvalidFrames(bool fragmented)
        {
            var path = Path.Combine(Application.dataPath, "../../mtg_play/protocol/fixtures/text-frames-v1.json");
            var corpus = JObject.Parse(File.ReadAllText(path));
            Assert.That((int)corpus["max_bytes"], Is.EqualTo(TextFrame.MaxBytes));
            Assert.That((int)corpus["framing_version"], Is.EqualTo(1));
            foreach (var test in corpus["positive"])
            {
                var bytes = Hex((string)test["hex"]);
                using var input = new Fragmented(bytes, fragmented);
                using var output = new MemoryStream();
                foreach (var message in test["messages"])
                {
                    Assert.That(TextFrame.Read(input), Is.EqualTo((string)message), (string)test["name"]);
                    TextFrame.Write(output, (string)message);
                }
                Assert.That(TextFrame.Read(input), Is.Null);
                Assert.That(output.ToArray(), Is.EqualTo(bytes));
            }
            foreach (var test in corpus["negative"])
            {
                using var input = new Fragmented(Hex((string)test["hex"]), fragmented);
                var error = Assert.Throws<TextFrame.FrameException>(() => TextFrame.Read(input), (string)test["name"]);
                Assert.That(error.Code, Is.EqualTo((string)test["code"]));
                Assert.That(error.Message, Is.EqualTo(error.Code), "No raw payload in diagnostics");
            }
        }
        [Test] public void MaximumFrameRoundTrips()
        {
            string text = new string('a', TextFrame.MaxBytes);
            using var stream = new MemoryStream();
            TextFrame.Write(stream, text); stream.Position = 0;
            Assert.That(TextFrame.Read(stream), Is.EqualTo(text));
        }
        [Test] public void InvalidWritesEmitNoPartialFrame()
        {
            foreach (var text in new[] { "", new string('a', TextFrame.MaxBytes + 1), new string('火', TextFrame.MaxBytes / 3 + 1), "\uD800", "\uFEFF{}" })
            {
                using var stream = new MemoryStream();
                Assert.Throws<TextFrame.FrameException>(() => TextFrame.Write(stream, text));
                Assert.That(stream.Length, Is.Zero);
            }
        }
    }
}
