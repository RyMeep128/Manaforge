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

Source-only preview: Play is enabled by default when running this branch from
source, including its homepage tile and navigation entry. Set
`MANAFORGE_ENABLE_LOCAL_PLAY=0` to hide it during development. Frozen/installed
builds keep Play disabled even when the environment variable is present. Opening
Play loads saved deck metadata; only **Start Game** starts the optional runtime.
No runtime is downloaded, upgraded or bundled by this change.

## Milestones B–D: interactive table

Implemented, awaiting CI and visual verification:

- Distinct object widgets in a two-player battlefield, grouped lands/permanents,
  current-seat hand, stack, graveyards, exile, command zones and revealed choices.
- Direct single-action card clicks, explicit action buttons when alternatives
  exist, and right-click inspection without taking an action. Every command is
  bound to the exact displayed snapshot and decision; stale controls cannot answer
  a later prompt.
- Boolean/mulligan, selection, target, ability/order, option, number, mana,
  amount-allocation and pile prompts. Target selection/deselection, finishing and
  cancellation use the engine's supplied choices and permissions. Unsupported
  families show a recovery message. No player decisions are automatically answered.
- Turn/phase/priority, stack objects, attacker/blocker controls and combat
  assignments. Mana requests permit source selection through the adapter's public
  payment contract; exhaustive legal-source enumeration is not available.
- Original-printing images from the existing image reader, active-face loading,
  bounded seat-scoped caches, tapped/counter/damage badges and live inspection.
  Engine card notes are explicitly labelled as potentially incomplete.
- Commander identities, command-zone cast information, additional costs and
  commander damage when supplied by the engine.
- Neutral, explicit seat handoff. Old hand widgets, decision handlers, inspection,
  observations and image caches are cleared immediately. Obsolete in-flight image
  replies cannot populate the next view. This is pass-and-play privacy, not authentication.
- Concession, authoritative result display and asynchronous cleanup, including
  waiting for artwork readers without blocking the UI.

Normal polling uses quiet jobs so it does not flash the global loading indicator
or write repeated operation-history entries. Other modules retain normal job behavior.

Deck selection currently lists saved native documents from the existing deck
catalog. Print projects must be saved as native decks through existing Editor
workflows first. Setup shows saved cover artwork and locally available color
metadata; missing metadata remains unknown instead of inventing deck information.
Unsupported entries are rejected by the adapter; no fallback deck is fabricated.

## Acceptance status

| Milestone | Stories | Status |
| --- | --- | --- |
| A | 1–3 | Implemented; CI pending |
| B | 4–6 | Implemented; CI and visual verification pending |
| C | 7–8 | Implemented; real-engine UI verification pending |
| D | 9–10 | Implemented; Commander/privacy/artwork verification pending |
| E | 11–12 | Scripted and pinned-engine UI acceptance wired; passing evidence still required |

No milestone is accepted solely because its code exists. In particular, do not
claim that a complete game has been demonstrated until CI and visual review
provide that evidence. Presentation tests cover fallback artwork; real selected
artwork and moderately crowded tables still require visual review.

### Verification paths

The existing Windows/Python test job collects the new Qt offscreen tests. These
cover lazy navigation, saved document preservation, obsolete replies and controls,
snapshot unavailability, decision families/constraints, uncertain outcomes, hidden
hands and faces, artwork fallback, object replacement, combat presentation and
cleanup. A prescribed ScriptedGameSession also drives the real homepage, setup,
card/action controls, seat handoff, concession and result display end to end.

The pinned-engine preparation step is reused by a new **Verify local Play through
Manaforge controls** step. `mtg_play.ui_acceptance` runs the existing `basic`,
`combat`, `blockers` and `commander-play` fixture policies through a UI pilot. The
pilot selects saved fixture decks, answers prompts using actual buttons/spinners,
hands off between seats through the neutral screen, and confirms the visible hand
matches the authorized snapshot. The production controller remains the sole owner
of engine communication. No test policy or automatic-answer code is imported by
the product workspace.

These scenarios retain their existing evidence gates; they end with explicit
concession after those gates, rather than claiming a natural victory. They are
not a duplicate rules test suite. Sanitized `ui-*.json` reports and bounded fixture
screenshots (setup, table, handoff, stack, combat and result) join the existing
XMage CI artifacts. Synthetic printing IDs intentionally exercise fallback art;
these screenshots do not establish real artwork quality or all printing styles.

The new pilot and scripted tests have not been executed during this task. Their
CI results may identify integration fixes. Full complex-board UI interactions,
real artwork appearance, crowding/focus usability, and every combined Freeform or
Commander interaction remain acceptance work. Existing headless real-deck and
complex-board evidence is still independently required. Installed Play must remain
disabled until those gates and visual review are satisfied.

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
