using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Public, offline renderer diagnostics only. Never accepts a live session snapshot.
    // No Unity APIs: all file IO, parsing and integrity work executes on a worker.
    public sealed class ArtworkFixture
    {
        public sealed class Asset
        {
            public int Width { get; }
            public int Height { get; }
            private readonly byte[] pixels;
            internal Asset(int width, int height, byte[] bytes)
            { Width = width; Height = height; pixels = bytes; }
            public byte[] CopyPixels() => (byte[])pixels.Clone();
        }
        public sealed class Card
        {
            public CardVisualIdentity Identity { get; }
            public CardDisplayValues MockValues { get; }
            public Asset Artwork { get; }
            internal Card(CardVisualIdentity identity, CardDisplayValues values, Asset artwork)
            { Identity = identity; MockValues = values; Artwork = artwork; }
        }
        public IReadOnlyList<Card> Cards { get; }
        public long RawBytes { get; }
        private ArtworkFixture(List<Card> cards, long bytes)
        { Cards = cards.AsReadOnly(); RawBytes = bytes; }

        public static Task<ArtworkFixture> LoadAsync(string directory, CancellationToken cancellation = default)
            => Task.Run(() => Load(directory, cancellation), cancellation);

        private static readonly Regex Hash = new Regex("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
        private static IOException Invalid() => new IOException("ARTWORK_FIXTURE_INVALID");
        private static string Text(JToken value)
        {
            if (value?.Type != JTokenType.String || value.Value<string>().Length > 16384) throw Invalid();
            return value.Value<string>();
        }
        private static string Optional(JToken value) => value?.Type == JTokenType.Null ? null : Text(value);
        private static int Number(JToken value, int maximum)
        {
            if (value?.Type != JTokenType.Integer || value.Value<long>() < 0 || value.Value<long>() > maximum) throw Invalid();
            return value.Value<int>();
        }
        private static bool Flag(JToken value)
        { if (value?.Type != JTokenType.Boolean) throw Invalid(); return value.Value<bool>(); }
        private static JArray Array(JToken value, int maximum)
        { if (!(value is JArray a) || a.Count < 1 || a.Count > maximum) throw Invalid(); return a; }
        private static void Fields(JToken value, params string[] names)
        {
            if (!(value is JObject obj) || !obj.Properties().Select(p => p.Name).OrderBy(x => x)
                .SequenceEqual(names.OrderBy(x => x))) throw Invalid();
        }
        private static byte[] Read(string path, int maximum, CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            // Reject linked files/directories; resources must be direct children of this bundle.
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw Invalid();
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (stream.Length < 1 || stream.Length > maximum) throw Invalid();
                var bytes = new byte[(int)stream.Length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    cancellation.ThrowIfCancellationRequested();
                    int read = stream.Read(bytes, offset, Math.Min(65536, bytes.Length - offset));
                    if (read == 0) throw Invalid();
                    offset += read;
                }
                return bytes;
            }
        }
        private static string Digest(byte[] bytes)
        { using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }

        private static ArtworkFixture Load(string directory, CancellationToken cancellation)
        {
            var root = new DirectoryInfo(Path.GetFullPath(directory));
            for (var parent = root; parent != null; parent = parent.Parent)
                if ((parent.Attributes & FileAttributes.ReparsePoint) != 0) throw Invalid();
            var manifest = WireEnvelope.ParseObject(new UTF8Encoding(false, true).GetString(
                Read(Path.Combine(root.FullName, "manifest.json"), 1024 * 1024, cancellation)));
            Fields(manifest, "fixture_version", "fixture_only", "description", "assets", "cards");
            int version=Number(manifest["fixture_version"],2);
            if(version<1 || !Flag(manifest["fixture_only"]))throw Invalid();
            Text(manifest["description"]);
            var assets = new Dictionary<string, Asset>(StringComparer.Ordinal);
            long total = 0;
            foreach (var item in Array(manifest["assets"], 48))
            {
                Fields(item, "asset_id", "file", "width", "height", "byte_length", "sha256", "pixel_format", "row_origin");
                string id = Text(item["asset_id"]), digest = Text(item["sha256"]);
                if (!Hash.IsMatch(id) || !Hash.IsMatch(digest) || Text(item["file"]) != id + ".rgba"
                    || Text(item["pixel_format"]) != "RGBA8" || Text(item["row_origin"]) != "bottom_left") throw Invalid();
                int w = Number(item["width"], 1024), h = Number(item["height"], 1024);
                int length = Number(item["byte_length"], 4 * 1024 * 1024);
                if (w == 0 || h == 0 || length != w * h * 4 || assets.ContainsKey(id)
                    || (total += length) > 64 * 1024 * 1024) throw Invalid();
                var bytes = Read(Path.Combine(root.FullName, id + ".rgba"), length, cancellation);
                if (bytes.Length != length || Digest(bytes) != digest) throw Invalid();
                var identityBytes = new byte[8 + length];
                for (int i = 0; i < 4; i++)
                { identityBytes[i] = (byte)(w >> (24 - i * 8)); identityBytes[4 + i] = (byte)(h >> (24 - i * 8)); }
                Buffer.BlockCopy(bytes, 0, identityBytes, 8, length);
                if (Digest(identityBytes) != id) throw Invalid();
                assets.Add(id, new Asset(w, h, bytes));
            }
            var cards = new List<Card>();
            foreach (var item in Array(manifest["cards"], 32))
            {
                cancellation.ThrowIfCancellationRequested();
                if(version==1)Fields(item, "oracle_id", "selected_printing_id", "selected_face", "values_source", "mock_values", "candidates");
                else Fields(item, "oracle_id", "selected_printing_id", "selected_face", "values_source", "layout", "mock_values", "candidates");
                if (Text(item["values_source"]) != "printed_reference_mock") throw Invalid();
                string oracle = Text(item["oracle_id"]), selectedId = Text(item["selected_printing_id"]), face = Text(item["selected_face"]);
                var candidates = new List<VisualPrintingCandidate>();
                var art = new Dictionary<string, Asset>(StringComparer.Ordinal);
                foreach (var candidate in Array(item["candidates"], 2048))
                {
                    Fields(candidate, "oracle_id", "printing_id", "face_key", "face_index", "standard_compatible", "cached", "asset_id");
                    string printing = Text(candidate["printing_id"]);
                    if (Text(candidate["oracle_id"]) != oracle || Text(candidate["face_key"]) != face || art.ContainsKey(printing)) throw Invalid();
                    Number(candidate["face_index"], 16);
                    bool cached = Flag(candidate["cached"]);
                    string assetId = Optional(candidate["asset_id"]);
                    if (cached != (assetId != null) || (cached && !assets.ContainsKey(assetId))) throw Invalid();
                    art.Add(printing, cached ? assets[assetId] : null);
                    candidates.Add(new VisualPrintingCandidate(oracle, printing, face, Flag(candidate["standard_compatible"]), cached));
                }
                var selected = candidates.SingleOrDefault(c => c.PrintingId == selectedId);
                if (selected == null) throw Invalid();
                var identity = VisualPrintingPolicy.Resolve(false, selected, candidates);
                var values = item["mock_values"];
                if(version==1)Fields(values, "name", "mana_cost", "type_line", "oracle_text", "power", "toughness");
                else Fields(values, "name", "mana_cost", "type_line", "oracle_text", "power", "toughness", "loyalty", "defense");
                string power = Optional(values["power"]), toughness = Optional(values["toughness"]);
                cards.Add(new Card(identity, new CardDisplayValues(Optional(values["name"]), Optional(values["mana_cost"]),
                    Optional(values["type_line"]), Optional(values["oracle_text"]),
                    power == null || toughness == null ? null : power + "/" + toughness, "PRINTED MOCK",
                    version==2?CardCompactProfile.FromMetadata(Text(item["layout"]),Optional(values["type_line"])):null,
                    version==2?Optional(values["loyalty"]):null,version==2?Optional(values["defense"]):null),
                    identity.MissingAsset ? null : art[identity.RenderedPrintingId]));
            }
            return new ArtworkFixture(cards, total);
        }
    }
}
