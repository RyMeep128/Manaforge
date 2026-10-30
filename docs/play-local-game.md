# Manaforge Play - local delivery and acceptance status

The [AI and Focused View rebuild epic](play-ai-focused-view-epic.md) is the
current delivery plan. Its first target is one local human versus one XMage AI,
followed by a format-first lobby, local asset preparation, and an immersive
two-player Focused View. The [long-term Play epic](manaforge-play-epic.md)
retains the future 2-5-player and private networking roadmap.

## Rebuild baseline - October 29, 2026

Branch: `feature/play-ai-focused-view`, based on current `origin/main` at
`fb27c2e` (`0.5.0-alpha.1`). This documentation increment records the requested
replacement experience; it does not implement AI or change the active UI.

### Story 1 increment: Freeform AI integration (CI pending)

The adapter accepts an optional seat controller (`local_human` by default or
`engine_ai`). Existing all-human 2-5-seat regression setups retain their previous
behavior. Initial AI setups require exactly one local human followed by one AI;
this is a capability restriction, not a protocol-wide player maximum. Remote
controllers are unsupported.

The bridge uses pinned XMage `COMPUTER_MAD`, the engine's existing AI controller,
and joins its selected deck through the human table owner's session before the
human joins. No second bridge client is created for AI. AI identity maps through
its generated public player name; it receives no private Manaforge view or command
channel. Public attempts to inspect or command the AI seat are rejected.

The new `ai-freeform` headless scenario is wired into existing pinned-engine CI.
Its fixture pilot controls only the human: keep the opening hand, play lands,
cast one Memnite, and pass while leaving AI attacks unblocked. Required evidence
includes AI lands, resolved creatures, turn advancement, combat, a natural human
loss, unchanged source documents, rejection of AI-seat access, no peer client,
and confirmed runtime cleanup without forced termination. A timeout or missing
evidence fails the scenario. This is fixture coverage, not a claim of arbitrary
deck strength or comprehensive card support.

The pinned upstream interfaces were inspected at `xmage_1.4.62V1`:
[PlayerType](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage/src/main/java/mage/players/PlayerType.java),
[NewTableDialog](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage.Client/src/main/java/mage/client/dialog/NewTableDialog.java),
and [TableController](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage.Server/src/main/java/mage/server/TableController.java).
The unchanged artifact integrity checks and CI compilation against the actual
pinned bundle remain authoritative; source inspection is not runtime evidence.

Story 1 is **not accepted**. Freeform CI evidence is pending. Two-player Commander
AI acceptance, explicit AI blocking coverage, and wider deck behavior remain
outstanding. The active UI still uses pass-and-play; no rebuilt gameplay UI or
installed feature enablement depends on this unverified integration.

No local tests, builds, or engine acceptance are permitted for this rebuild.
New tests execute in GitHub Actions; identify actual runs before claiming a pass.
Installed Play remains gated until the full acceptance and manual UX review pass.
No engine pin, compatibility manifest, saved deck, or existing printing identity
is changed by this baseline. No release, tag, or merge is part of this increment.

## Existing pass-and-play implementation (historical baseline)

The sections below describe the existing source preview and its recorded
verification gaps. They are not acceptance evidence for the AI rebuild. Active
pass-and-play and handoff UI will be removed in the seat/controller story after
the Story 1 AI gate; existing privacy and lifecycle regression coverage must be
retained or adapted.

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
