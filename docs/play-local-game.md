# Manaforge Play - local delivery and acceptance status

The [AI and Focused View rebuild epic](play-ai-focused-view-epic.md) is the
current delivery plan. Its first target is one local human versus one XMage AI,
followed by a format-first lobby, local asset preparation, and an immersive
two-player Focused View. The [long-term Play epic](manaforge-play-epic.md)
retains the future 2-5-player and private networking roadmap.

## Current offline preview workflow

Open **Play Offline**, choose Freeform or Commander, then **Continue to Lobby**.
Choose your deck and the AI deck. **Randomize** starts an explicit offline engine
preflight and chooses only among decks that pass the pinned engine's checks.
Local readiness labels alone are not engine eligibility certificates. Display-only
commander entries are omitted for all precons; playable deck documents and exact
printing choices are preserved. Unsupported cards or exact printings can still
prevent a match from starting.

**Start Game** prepares cached artwork and battlefield crops on a worker. If any
artwork is missing, review the list and choose **Continue Anyway** for placeholders
or **Return to Lobby** to keep your selections. Gameplay and inspection use frozen
local image references and do not fetch missing artwork. Generated objects without
a prepared local reference use placeholders.

The match loading page shows real stages and elapsed time. Cancel requests stop
startup waits and then clean up owned processes; an already-running synchronous
preparation/compilation step must finish before cleanup. Unconfirmed cleanup blocks
new matches and offers a retry. Match entry maximizes the containing window and
leaving gameplay restores its previous window state.

Choose Keep/Mulligan only for your human seat; the AI makes its own choices. Bottom
selections and their completion/cancellation permissions come from the engine.
Focused View keeps your hand below both battlefields, with contextual stack and
combat information. Hover for a full printing and live engine details; right click
for persistent inspection. A single legal action is direct; multiple actions open
a menu. Printed artwork is not a promise that printed characteristics are current.

Finished matches show the engine's outcome and **Return to Lobby**. A non-winning
result is not reinterpreted as a specific loss/draw reason. Failed or uncertain
sessions offer cleanup recovery rather than replaying a command. **Copy Play
diagnostics** and **Report a Play issue** provide bounded version/stage/error data;
the shared feedback composer retains its review and consent controls.

Host Match, Join Match and Invite Friend remain unavailable. Opening Play does not
start XMage. Installed builds remain gated. Source implementation and focused unit
verification do not establish full epic acceptance.

## Acceptance evidence and nightly visual review

The CI UI pilot retains the fixed human-versus-AI fixture scenarios and records
lobby, format, setup, loading, missing artwork, opening hand, hover context/popup,
observed choices, stack, combat, result, cleanup and lobby-return screenshots as
those views occur. Its report lists actual screenshots, attempted remote image
fallbacks and lobby return. Successful runs require key navigation/opening/hover/
return artifacts. The pilot verifies that hovering submits no command and that
returning after cleanup preserves deck selections. Synthetic fixture artwork still
exercises placeholders; it does **not** substitute for real printing visual QA.

Manual nightly review remains required with ordinary cached decks and real images:

1. Check format/lobby actions at 1024x768 and 1280x720 or larger. Verify visible
   readiness reasons and loading feedback while Randomize and Start prepare work.
2. Try a fully cached deck and one missing artwork. Review Continue Anyway/Return,
   selected printing identity, commander and partner artwork, and cancellation.
3. Inspect actual battlefield crops, full hover previews, transformed/flip faces,
   live stat/counter changes, and hidden-card privacy. Confirm hovering/right click
   never submits a decision.
4. Complete human opening choices and any required bottom selections. Play a land
   and spell, pay offered costs, pass priority, attack/block and inspect the stack.
5. Reach an authoritative result, return to the lobby and verify selections/window
   state and cleanup. Exercise failed-start and cleanup-retry recovery separately.
6. Review optional diagnostics before sharing. Report missing images, clipping,
   confusing prompts and unsupported cards without marking the epic accepted.

### Offline real-printing crop review

A local review command renders a full cached printing beside its battlefield crop,
including alternate or flip faces when supplied. It starts no engine, performs no
download, leaves source files unchanged, and writes a PNG plus a small digest report
into a **new** output directory. This is image-review evidence, not gameplay proof.

From `Mtg_Projects`, using the Python environment with the application dependencies:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONPATH = "$PWD;$PWD\mtg_core"
py -3.13 -m mtg_play.artwork_review --printing-id '<printing UUID>' --front 'C:\cache\front.png' --output 'C:\review\new-printing-review'
```

Use the exact printing UUID and an existing full image from your local cache.
For separate double-faced images add `--layout transform --back 'C:\cache\back.png'`
(or `--layout modal_dfc`). For a classic shared-image flip card use `--layout flip`
without a separate back. Missing/corrupt source faces fail rather than downloading
or silently substituting a different printing. Existing output directories are
rejected. Review `artwork-review.png` and `review.json`; do not treat the report as
an engine validation or manual game-completion sign-off.

The generic crop now uses rendering version `battlefield-2` and the upper 54 percent
of the source image. Real-printing inspection found that the earlier 58 percent crop
could retain a thin rules-text strip. The new version invalidates old derivatives
for every printing; unusual frames may still crop imperfectly.

Historical implementation notes below describe earlier increments and their state
at the time. They are not a current claim that every outstanding criterion passed.

## Rebuild baseline - October 29, 2026

Branch: `feature/play-ai-focused-view`, based on current `origin/main` at
`fb27c2e` (`0.5.0-alpha.1`). The original documentation increment recorded the
requested replacement experience without changing the UI. Subsequent local
implementation increments and their verification gaps are recorded below.

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

### Story 1 follow-on: Commander and blocking evidence (local, unverified)

Two additional scenarios are prepared for a subsequent CI run:

- `ai-commander`: canonical 99 Plains plus Isamaru documents for both seats.
  Require both command zones, preserved commander printing identities, AI casting
  its commander from the command zone, combat, commander damage to the human,
  a human land play, and an engine-offered human commander cast action. The human
  leaves its commander uncast to permit AI attacks against an open battlefield.
- `ai-blockers`: one human Memnite attacks into engine-controlled Ornithopters.
  Require the actual human attacker and AI blocker references in the same blocked
  combat assignment. Merely having an AI creature or unrelated combat is not proof.

Both drivers control only the human, reject unknown human decisions, and concede
only after their evidence gates. Reports explicitly distinguish these conceded
outcomes from the Freeform normal-completion proof. Both must confirm the human's
non-winning result, unchanged source documents, and normal owned-process cleanup
without an AI peer client. Fixture driver tests cover evidence ordering, rejection
of premature results and unrelated combat, and canonical Commander preservation.
AI strategy is not overridden if it declines to block; missing evidence fails CI.

The first Freeform increment failed in
[CI run 40977624067](https://github.com/RyMeep128/Manaforge/actions/runs/40977624067)
at `ef38464050689315480d033dd87dee18f96171ce`. The user requested investigation;
no further push or automatic CI monitoring is authorized. The local follow-on
scenarios and later UI/lifecycle changes were not part of that run.

The Python 3.12 and 3.13 application suites passed, as did lint/format checks,
the other 25 headless XMage scenarios (including 2-5-seat Commander), and all four
legacy UI scenarios. The new `ai-freeform` pilot failed with
`AI_ACCEPTANCE_UNSUPPORTED_DECISION`. Its artifact confirms normal bridge/server
exit codes of zero, no peer client, and no forced cleanup:
[XMage acceptance artifact](https://github.com/RyMeep128/Manaforge/actions/runs/40977624067/artifacts/12944488011).

The redacted transcript contains 73 acknowledged human responses, ending with
an unanswered `GAME_TARGET`. It deliberately excludes private prompt/card data,
so it does not prove the final prompt text. The leading diagnosis is a cleanup
discard: the fixture casts only one Memnite, keeps drawing cards, and had no
human discard handler. The fixture has no targeted spells and does not select
attackers or blockers, while pinned XMage's
[cleanup step](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage/src/main/java/mage/game/turn/CleanupStep.java)
requests discards to maximum hand size.

The local fix adds a shared CI-only discard policy using the current decision
token and an engine-offered, unselected card from the visible human hand. It
cannot select AI, hidden, or unoffered cards, and it does not answer unrelated
target prompts. Production human decisions remain manual. Unknown fixture choices
now report only an allowlisted family and option/hand-option counts, without
prompts, names, labels, object IDs, or deck contents; their diagnostic category is
`acceptance_pilot_gap`. Regression tests cover these restrictions, a prescribed
Freeform discard-to-normal-result sequence, and a discard through actual UI
controls. None of these tests has run locally.

Story 1 is **not accepted**. The Freeform fix requires a fresh CI result; no
normal completed AI match has yet been demonstrated. Commander/blocking and the
later fixed-view source workspace remain unverified local work. The previous
expected-green assumption is superseded by the recorded failure. Installed Play
remains disabled, and further feature expansion must not be treated as acceptance.

No local tests, builds, or engine acceptance are permitted for this rebuild.
New tests execute in GitHub Actions; identify actual runs before claiming a pass.
Installed Play remains gated until the full acceptance and manual UX review pass.
No engine pin, compatibility manifest, saved deck, or existing printing identity
is changed by this baseline. No release, tag, or merge is part of this increment.

### CI follow-up: outdated document-identity assertion

At the user's failure report, the pushed `e6f9e1a9b888eb2253662b85b2f1df134260ac4f`
run had a completed Python 3.13 job with **1 failed, 1,744 passed**:
[run 40981801955, Python 3.13](https://github.com/RyMeep128/Manaforge/actions/runs/40981801955/job/123823372643).
The failing `test_start_is_lazy_and_all_engine_calls_are_off_ui_thread` still
required `owner.decks is documents`, contradicting the intentional worker-owned,
per-seat document copies added by Story 2. The production copying behavior is
retained. The test now requires distinct tuple/document identities, unchanged
serialized contents in source and match documents, and cleanup even if an assertion
fails. Existing deep-mutation isolation and worker-thread checks remain intact.

The Python 3.12 application's test step had also failed in the inspected job
summary, while its pinned-engine acceptance was still running. No engine outcome
is inferred from that partial run, and no further monitoring or rerun was performed.
The newer landing/readiness commits were not present in this pushed run. This
assertion fix is local and unverified; no local tests or builds were executed and
no push is authorized by the investigation.

### Story 2 increment: independent seats and a fixed human view (local, unverified)

The active setup labels the seats **You** and **Opponent**. The opponent uses
**Use AI**; **Invite Friend - Coming Soon** is visible and disabled. There is no
active pass-and-play, seat-handoff screen, or opponent-hand reveal action. Both
Freeform and Commander initially used the existing setup page; the subsequent
landing/navigation increment below now requires format confirmation first. Full
lobby eligibility and borrowed-library integration remain later work.

`lobby.py` separates match-seat identity, player identity, pilot/controller,
canonical deck identity, and optional deck owner. Ownership is not inferred from
piloting or written into saved Core documents. A borrowed deck can retain an
owner distinct from its human or AI pilot. Engine session identity stays in the
session controller, separate from this preparation model. Only the engine-facing
seat name/controller and canonical deck snapshots cross the adapter boundary.

The offline request requires one local human followed by one engine AI. The
shared lobby model can represent larger mixed tables and reserves RemoteHuman
without implementing networking or imposing a five-seat protocol maximum.
Existing headless all-human 2-5-seat adapter regressions remain in CI.

The product controller is bound to the local human's authorized viewer. It cannot
switch to the AI seat or submit/concede using a foreign view. The generic
controller's all-human seat-switch privacy and uncertain-command regressions
remain as boundary coverage, independent of the removed handoff UI.

Each selected Core document is copied independently on the background worker
before engine submission. Selecting the same saved deck for both seats therefore
creates two isolated in-memory match copies while preserving deck IDs, selected
printings, commander selections, preferences, and owner metadata in the lobby.
No deck is saved, transferred to a pilot, or converted to a persistent match format.

The UI pilot now runs `ai-freeform`, `ai-commander`, and `ai-blockers` through the
fixed human controls. It rejects AI-seat inspection/commands and captures setup,
loading, opening hand, battlefield, stack, combat, and result states when reached.
The previous pass-and-play UI scenarios are retired; their headless rules scenarios,
hidden-information regressions, and lifecycle coverage remain. The prescribed UI
fixture now covers human choices and permitted AI battlefield frames without
inventing AI decisions or rules.

New lobby/Qt tests cover independent ownership, larger-table representation,
foreign-view rejection, absence of active handoff controls, and per-seat document
isolation. **Story 2 remains unaccepted** until CI and manual review verify the
updated workflow. The UI still uses the earlier table renderer and artwork loader;
this increment does not establish strict offline asset loading, Focused View,
full lobby validation, or overall playability.

### Story 4 increment: landing and shared format-first navigation (local, unverified)

The landing page prominently offers **Play** and **Play Offline**, with unavailable
**Host Match** and **Join Match** grouped on the right at desktop widths. On smaller
widths that group moves below the main panel within a scrollable page. Typography,
panel styling, and colors reuse Manaforge's visual language. The decorative card
fan is drawn locally with Qt; it performs no artwork/metadata requests and uses
no proprietary game assets.

Play opens mode selection; Play Offline enters the offline format step directly.
Both use the same format picker, lobby model, deck selection widgets, preparation
controller, and startup path. The initial format prompt has no selection. Deck
controls remain unavailable until the user confirms Freeform or Commander and
enters the lobby. Start Game cannot launch a retained selection from the landing
or format pages.

Back navigation preserves the existing lobby selections. Cancelling a format
change restores the previous confirmed format; confirming a different format
retains the chosen decks and displays the existing incompatibility warnings rather
than silently substituting decks. The lobby is scrollable and the page stack uses
only its current page's size hints, so hidden battlefield minimum sizes do not
force an oversized landing window. Home navigation remains available.

The UI acceptance pilot now clicks through landing, format confirmation, and the
shared lobby before starting its AI scenarios, with landing and format screenshots
added to its existing capture points. Added Qt regressions cover both entry paths,
format gating/back/cancel behavior, retained deck selections, disabled network
controls, lazy runtime construction, and primary-control visibility at 1280x720
and 1024x768. These tests and screenshots have not been executed locally.

**Story 4 remains unaccepted** pending CI and visual/manual UX review. This increment
also implements the navigation portion of Story 5, but does not claim full deck
eligibility, shared-library borrowing, randomization, asset preflight, strict
offline gameplay, or Focused View. Continued local development uses expected green
CI as the user's working assumption; no new CI result has been inspected or claimed.

### Story 5 increment: local readiness and cached shared decks (local, unverified)

Lobby preparation runs on the catalog worker and reports real completed-deck
counts. It reuses the adapter's structural checks and Core's local Commander
checker rather than introducing Magic rules in Qt. Known problems disable Start
Game; incomplete, malformed, undated, or stale local card data stays a visible
review state unless Core also finds a blocking problem. Freeform receives structural
checks without imposing Standard/Modern constructed restrictions. A failing local
metadata database is not retried once per deck in the same preparation job.

The labels deliberately distinguish local checks from engine validation. Missing
Oracle resolution, unsupported engine cards, printing mismatches, and engine deck
legality remain authoritative startup checks. Local availability is **not** proof
of pinned-engine support and must not be used alone as a Randomize eligibility
certificate. No card, printing, commander choice, or saved format is substituted.
Core error categories are displayed without exposing an opponent's individual
private card names or entry identities.

Commander names and artwork keys come from Core's active commander selections.
The lobby uses the selected printing/custom image key for each of up to two
commanders, preserving separate partner previews. Missing art remains a placeholder;
full asset preparation and the strict gameplay network policy belong to Story 8.

**Browse shared decks** opens the existing Browse Online module before the match.
Follow a deck there, return to Play, and choose **Refresh decks**. Play reads the
accepted local FollowedDecks snapshot; it does not sign in, contact a library,
check for updates, accept pending revisions, or create new sharing infrastructure.
Already accepted caches remain selectable when the library is offline. The visible
source/owner label distinguishes cached shared decks from saved native documents.

Each cached source has a stable library/deck selection key, independent of its
canonical local DeckDocument ID. Its owner reference namespaces the accepted
publication's public owner handle by server; it is provenance, not a RemoteHuman
authentication identity. Lobby ownership remains independent of the human/AI pilot.
The existing worker makes isolated per-seat match copies. Play does not save or
modify the shared source, its accepted revision, pending update, or owner's deck.
Refreshing the catalog preserves the selected source keys and owner references.

Added tests cover local/engine validation boundaries, malformed quantities and
partial metadata, Core Commander failures, exact commander-art keys and partners,
worker-thread metadata reads, blocking known-invalid starts, preserved selections,
accepted-versus-pending shared revisions, network-denied cache reads, source
immutability, and navigation into the existing library workspace. Synthetic UI
decks now contain their land/creature fixture cards and valid Commander counts;
production validation is not relaxed for test fixtures.

**Story 5 remains unaccepted** pending CI and manual UX/artwork review. No tests,
builds, or engine acceptance were run locally, and no new CI result was monitored.
This increment does not provide pre-certified pinned-engine deck eligibility,
Randomize, asset manifests, gameplay artwork isolation, or completed AI-match proof.

### Story 3 increment: measured startup and readiness (local, unverified)

The runtime and adapter report actual work stages: runtime validation, workspace
preparation, bridge compilation, server startup, client connection, engine
handshake, deck resolution, player connections, table creation, deck submission,
match start, runtime disconnection, and process cleanup. Presentation also tracks
waiting for the first authorized game state. The existing status label receives
stage descriptions through queued Qt signals; no percentage or simulated progress
is introduced. This is lifecycle feedback, not the final loading-screen design.

Lifecycle diagnostics retain at most 128 events with fixed stage/state identifiers,
measured elapsed milliseconds, and stable `PLAY_<STAGE>_<FAILURE>` codes. Timeout
and uncertain outcomes are distinguished. These records are included in sanitized
adapter acceptance reports and the runtime result file. Failure logs contain
stage/timing codes rather than private exception messages or tracebacks. Observer
failures cannot interrupt engine work; stale UI epochs cannot overwrite a newer
session or a closing screen.

A 60-second readiness deadline applies after match creation. If no first snapshot
is available at the next failed readiness check after that deadline, worker-owned
cleanup runs before returning to setup. In-flight engine requests finish under
their existing timeouts; this is not a hard interruption of uncertain work.
Closing during the wait records cancellation. Later transient snapshot gaps retain
the existing recovery behavior and are not treated as a new opening-state timeout.

Processes explicitly reported as never started are omitted from the runtime's
exit-code list. Started processes with unconfirmed cleanup remain represented by
unknown exit codes, preventing an unsafe retry. Startup errors retain their
specific stage only after cleanup is confirmed. The existing ownership rules,
engine integrity checks, and prohibition on replaying uncertain commands remain.

Queue inspection found that artwork already has its own worker and refresh skips
submission while another gameplay job is queued/running. No shared queue rewrite
or additional polling backlog is introduced by this increment.

New tests cover measured/private-data-free failures, bounded history, broken
observers, compilation failure before any child starts, repeated failed startup
with confirmed/unconfirmed cleanup, queued GUI delivery, obsolete progress, and
opening-state timeout/retry. They have not run locally. Story 3 is **not accepted**:
real-engine repeated start/fail/retry/close evidence and full failure-path UX
review remain required. No CI results have been assumed as verified evidence.

## Existing pass-and-play implementation (historical baseline)

The sections below describe the existing source preview and its recorded
verification gaps. They are not acceptance evidence for the AI rebuild. The active
pass-and-play and handoff UI has now been removed under the user's instruction to
continue using green CI as a working assumption. Relevant privacy and lifecycle
regression coverage has been retained or adapted; no actual CI pass is claimed.

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
