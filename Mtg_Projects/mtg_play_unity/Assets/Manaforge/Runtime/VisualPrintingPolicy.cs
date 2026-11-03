using System;
using System.Collections.Generic;

namespace Manaforge.Play
{
    // Presentation-only metadata supplied by a trusted, viewer-scoped asset boundary.
    // StandardCompatible is an explicit catalog/profile classification, never inferred from rules.
    public sealed class VisualPrintingCandidate
    {
        public string OracleId { get; }
        public string PrintingId { get; }
        public string FaceKey { get; }
        public bool StandardCompatible { get; }
        public bool Cached { get; }

        public VisualPrintingCandidate(string oracleId, string printingId, string faceKey,
            bool standardCompatible, bool cached)
        {
            if (string.IsNullOrWhiteSpace(oracleId) || string.IsNullOrWhiteSpace(printingId)
                || string.IsNullOrWhiteSpace(faceKey)) throw new ArgumentException("Missing visual identity");
            OracleId = oracleId;
            PrintingId = printingId;
            FaceKey = faceKey;
            StandardCompatible = standardCompatible;
            Cached = cached;
        }
    }

    public sealed class CardVisualIdentity
    {
        public string OracleId { get; }
        public string SelectedPrintingId { get; }
        public string RenderedPrintingId { get; }
        public string RenderedFace { get; }
        public string LayoutProfileId { get; }
        public bool MissingAsset => RenderedPrintingId == null;

        internal CardVisualIdentity(VisualPrintingCandidate selected, VisualPrintingCandidate rendered)
        {
            OracleId = selected.OracleId;
            SelectedPrintingId = selected.PrintingId;
            RenderedPrintingId = rendered?.PrintingId;
            RenderedFace = rendered?.FaceKey;
            LayoutProfileId = rendered == null ? null :
                rendered.StandardCompatible ? "standard-v1" : "authentic-image-v1";
        }
    }

    public static class VisualPrintingPolicy
    {
        // Offline selection only: never reads files, downloads, or mutates preferences.
        // Call only after viewer filtering. Concealed input produces no retained identity.
        public static CardVisualIdentity Resolve(bool concealed, VisualPrintingCandidate selected,
            IEnumerable<VisualPrintingCandidate> candidates)
        {
            if (concealed) return null;
            if (selected == null) throw new ArgumentNullException(nameof(selected));
            if (candidates == null) throw new ArgumentNullException(nameof(candidates));
            VisualPrintingCandidate bestStandard = null;
            VisualPrintingCandidate bestAuthentic = null;
            foreach (var candidate in candidates)
            {
                if (candidate == null || !candidate.Cached
                    || candidate.OracleId != selected.OracleId || candidate.FaceKey != selected.FaceKey
                    || candidate.PrintingId == selected.PrintingId) continue;
                if (candidate.StandardCompatible && Earlier(candidate, bestStandard)) bestStandard = candidate;
                if (Earlier(candidate, bestAuthentic)) bestAuthentic = candidate;
            }
            var rendered = selected.StandardCompatible && selected.Cached ? selected :
                bestStandard ?? (selected.Cached ? selected : bestAuthentic);
            return new CardVisualIdentity(selected, rendered);
        }

        private static bool Earlier(VisualPrintingCandidate candidate, VisualPrintingCandidate current)
        {
            return current == null || string.CompareOrdinal(candidate.PrintingId, current.PrintingId) < 0;
        }
    }
}
