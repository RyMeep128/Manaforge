# Manaforge Play — first local two-player experience

This is the staged Phase 8 implementation of the local two-player epic. It takes
precedence over the broader future scope in [the long-term Play epic](manaforge-play-epic.md).
Remote multiplayer, AI, larger tables, dynamic card frames and public Play releases
are outside this delivery.

## Milestone A: foundation

Implemented, awaiting CI verification:

- Persistent, lazily created Play workspace through the existing ModuleController.
- Two local names, Freeform/Commander selection, and saved native Core decks.
- Deck documents retain selected printings, commander selections and other fields;
  startup sends isolated copies to the adapter without rewriting saved decks.
- Serialized background startup, polling, seat-specific snapshots, commands and
  shutdown using the shared Qt JobQueue. No engine communication runs on the UI thread.
- Obsolete view replies are discarded; unavailable snapshots clear the presentation.
  Submitted decisions remain pending until authoritative state changes, and uncertain
  commands require explicit session recovery rather than automatic replay.
- Home navigation preserves the workspace and session. Closing the application
  waits for owned engine cleanup and respects the game-close confirmation.
- Scripted session tests are collected by the existing Windows/Python CI suite.

Source-only preview: set `MANAFORGE_ENABLE_LOCAL_PLAY=1` before starting Manaforge.
This enables the existing homepage tile and navigation entry. Frozen/installed
builds keep Play disabled even when the environment variable is present. Opening
Play loads saved deck metadata; only **Start Game** starts the optional runtime.
No runtime is downloaded, upgraded or bundled by this change.

The foundation shows public player/turn status after startup. It does **not** yet
provide a playable battlefield or mulligan/decision controls. Do not treat this
workspace as the epic's gameplay acceptance result.

Deck selection currently lists saved native documents from the existing deck
catalog. Print projects must be saved as native decks through existing Editor
workflows first. Artwork/color previews belong to the next presentation stages.
Unsupported entries are rejected by the adapter; no fallback deck is fabricated.

## Remaining stages

| Milestone | Stories | Required result |
| --- | --- | --- |
| B | 4–6 | Battlefield, distinct card objects, legal actions and reusable player decisions |
| C | 7–8 | Stack responses, priority and interactive combat |
| D | 9–10 | Selected-printing artwork, live inspection, Commander information and neutral seat handoff |
| E | 11–12 | Lifecycle polish, negative scenarios and complete real-engine UI acceptance |

The controller's conceal/reveal boundary is groundwork for handoff. A finished
handoff screen, private artwork/overlay cleanup and two-player privacy acceptance
remain required before claiming Story 10 complete.

## Adapter evidence gate

Integration base: `3198da0a6be309832882bee4e0dc4be13f178c09` on
`feature/xmage-real-deck-validation`, including the optional-payment fix. The
existing adapter and pinned runtime/artifact manifest remain unchanged.

The [real-deck validation report](../Mtg_Projects/mtg_play/REAL_DECK_VALIDATION.md)
records the original scenario evidence and the outstanding new real-deck and
complex-board CI evidence. Connected workflow/status queries returned no entries
for the integration commit during implementation; that is not proof of a pass or
failure. The existing expensive scenarios stay in the pinned-engine CI environment.

No local test suites, builds, benchmarks or engine acceptance were run for this
stage. New offscreen tests and existing navigation/module regressions must pass CI.
Full end-to-end acceptance remains gated on both real-engine evidence and the
complete UI scenarios in Milestone E. No release, tag, push or merge is authorized
by this implementation.
