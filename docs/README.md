# Documentation

Start with the [project overview](../README.md) or [current roadmap](roadmap.md).
User guides describe workflows; implementation references describe narrower
components and retain their original versioned evidence. Historical plans and
reports are in the [archive](archive/README.md).

## Use Manaforge

| Task | Guide |
| --- | --- |
| Install, update, manage artwork, diagnose or recover | [Installation and updates](installation-and-updates.md) |
| Build and organize decks | [Deck Editor](../Mtg_Projects/mtg_editor/README.md), [deck setup](deck-setup.md), [discovery](deck-builder-discovery.md) |
| Understand local data and categories | [Card search](local-card-search.md), [categorization](card-categorization.md), [Card Database](card-database-workspace.md) |
| Prepare and print proxies | [Print guide](../Mtg_Projects/mtg_proxy/README.md), [printer setup](printing-roadmap.md), [card layouts](card-layout-support.md) |
| Explore preconstructed decks | [Preconstructed decks](preconstructed-decks.md) |
| Share through private libraries | [Library server and clients](self-hosted-library.md) |
| Play in Unity | [Play guide](play.md) |
| Send feedback or host the relay | [Feedback relay](../feedback-relay/README.md) |

## Develop and maintain

- [Workspace, commits, and CI evidence](development-workflow.md) and [repository instructions](../AGENTS.md).
- [Shared components](shared-components.md), [infrastructure](infrastructure-readiness.md), [print package](../Mtg_Projects/mtg_print/README.md).
- [Recommendation data](recommendation-data.md), [distribution](recommendation-distribution.md), [public deck collection](public-deck-collection.md).
- Collector operations: [Archidekt](archidekt-collection.md), [EDHREC](edhrec-collection.md), [Moxfield](moxfield-collection.md).
- [Unity project and build](../Mtg_Projects/mtg_play_unity/README.md), [launch package](../Mtg_Projects/mtg_play/README.md), [shared protocol index](../Mtg_Projects/mtg_play/protocol/README.md).

## Play implementation references

Current visual-overhaul direction: [reusable elements and default 1v1 composition](play.md#reusable-visual-elements-and-views).

These references remain separate because they describe distinct ownership,
protocol, renderer, and engine boundaries. A historical local pass count is not
current-revision CI or owner sign-off. See [Play acceptance](play.md#acceptance-and-references).

- [Arena-inspired live table visual pass](play-arena-visual-pass.md)
- [Arena live visual review — November 3, 2026](play-arena-visual-review.md)
- [Arena table — second visual sweep](play-arena-visual-sweep.md)
- [Offline real-artwork fixture preparation — G0/P3.2 foundation](play-artwork-fixtures.md)
- [Bounded artwork job coordinator](play-artwork-jobs.md)
- [Private bootstrap pipe and owner lifeline](play-bootstrap-pipe.md)
- [Cost and inline rules symbols](play-card-symbol-rendering.md)
- [Offline Core artwork provider](play-core-artwork-provider.md)
- [Authenticated host artwork-sidecar lifetime](play-host-artwork-lifecycle.md)
- [Play launch manifest — P1.3 foundation](play-launch-boundary.md)
- [Play launch ownership and lifecycle — P1.4 foundation](play-launch-lifecycle.md)
- [Specialized-layout renderer gallery](play-layout-gallery.md)
- [Live card text](play-live-card-text.md)
- [Live Unity / Java / XMage integration](play-live-integration.md)
- [Keep-first London mulligan engine follow-up](play-mulligan-engine-followup.md)
- [Launch-owned private bootstrap writing](play-owned-bootstrap-write.md)
- [Packaged Unity private-bootstrap proof](play-packaged-bootstrap-proof.md)
- [Safe automatic mana payment — Java coordinator](play-payment-coordinator.md)
- [Bounded viewer presentation pump](play-presentation-pump.md)
- [Automatic priority and Full Control](play-priority-control.md)
- [Owner-provided Wizards asset inventory](play-provided-art-assets.md)
- [Bounded render mailbox and UI drain](play-render-mailbox.md)
- [Packaged renderer measurements — G0/P0.3 partial evidence](play-renderer-benchmarks.md)
- [Terminal viewer-channel errors — P1.2/G1](play-session-errors.md)
- [Authenticated packaged session fixture](play-session-fixture.md)
- [Authorized single-face artwork binding](play-viewer-artwork.md)
- [Private Unity viewer bootstrap](play-viewer-bootstrap.md)
- [Bound viewer command dispatch](play-viewer-command-dispatch.md)
- [Viewer decision offer binding](play-viewer-decision-binding.md)
- [Viewer decision panel](play-viewer-decision-panel.md)
- [Immutable viewer decision projection](play-viewer-decisions.md)
- [Authenticated viewer session host](play-viewer-session-host.md)
- [Viewer session receive-to-presentation bridge](play-viewer-session-receiver.md)
- [Viewer card surface ownership](play-viewer-surface.md)
- [Checking installed XMage card coverage](play-xmage-card-support.md)
- [Manaforge XMage downstream](play-xmage-fork.md)
- [Arena-inspired library, graveyard and exile](play-zone-piles.md)
- [Automatic priority in Unity](unity-priority-passing.md)

## Documentation audit — November 3, 2026

The starting inventory contained **110 tracked Markdown files and 22,149 lines**
across the repository, including package guides and protocol references.
The main problems were competing roadmaps, long implementation journals mixed
with current instructions, duplicate setup/recovery material in the root README,
and obsolete Python/Qt gameplay and Unity foundation descriptions.

This cleanup moves **17 historical documents** into the archive, replaces the
root and Unity entry points with concise current guides, adds this index and a
current Play guide, and replaces the long delivery checklist with a short roadmap.
Original acceptance criteria remain available in the archive. Relocated local
Markdown links are updated and checked for target existence.

The remaining large live-integration and payment documents are implementation
journals, not user guides. Their versioned claims still need revision-specific
evidence; this audit does not re-certify them. Future work can extract durable
contracts from those journals as the corresponding behavior settles.

Keep one current guide per workflow. Update that guide when behavior changes;
avoid adding a new top-level story document for each increment. Archive dated
investigations and superseded plans, and link historical requirements explicitly.
