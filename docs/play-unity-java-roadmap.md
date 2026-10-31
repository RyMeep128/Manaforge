# Manaforge Play — Unity + Java Roadmap

Status: **Proposed architecture and implementation roadmap. All gates remain unproven.**

Planning baseline: Manaforge main at `fb27c2e` (`0.5.0-alpha.1`, October 29, 2026).
Documentation intake checkout: `28d0cef` (`0.5.29-alpha.1`); subsequent Qt work
remains a regression baseline, not evidence of Unity or Java parity.

Scope: replace Play's long-term presentation architecture. Do not rewrite Deck
Editor, Card Database, Printer, or the canonical deck model.

Target: **Unity (C#) → Manaforge-owned Java gameplay gateway → pinned XMage (Java).**

Development: Codex implements stories; CI validates; the owner reviews diffs,
artifacts and actual UX builds. Owner clarification: focused local tests and
checks are allowed; **do not run the full test suite locally**. CI evidence is
required before declaring a story complete.

## 1. Vision and non-negotiables

Build an Arena-like, rules-enforced Magic client for eventual 2–5-player Commander
while retaining Build → Discover → Print → Play, authentic printings and existing
decks. Owner clarification: first deliver local 1v1 **human versus XMage AI**,
then private networked 1v1 and 3–5-player Commander. Design the presentation for
up to five players from the beginning; this does not impose a five-seat wire maximum.

- XMage alone determines rules, state, legality, timing, costs, triggers, damage
  and outcomes. No duplicate rules engine in Unity, Java gateway or Python.
- Unity owns graphics, presentation, animation, interaction, visual state and UX.
  It must not import XMage types or reconstruct hidden or unsupported facts.
- A Manaforge-owned versioned protocol remains the public boundary across engine upgrades.
- Java replaces the Python gameplay adapter only after demonstrated parity.
  Python retains the application/library and optional one-time launch/deck export,
  but leaves the per-action gameplay loop.
- Preserve immutable viewer-filtered snapshots, ephemeral object identities,
  exact printing IDs, decision-token validation, private reveals and safe cleanup.
- Design variable seats from the start without implementing all multiplayer UI
  during 1v1. Controller type remains independent of seat count.
- Installed offline/local play requires no account, public server or cloud dependency.
- Use small reversible branches. Keep Python/Qt Play as an executable regression
  oracle and fallback until replacement acceptance. Preserve working Java integration.

## 2. Proposed runtime architecture

```text
Manaforge Desktop (Python/PyQt6)
  Deck Editor / Card DB / Printer / launch / one-time deck export
                         |
             versioned launch manifest + deck snapshots
                         v
Unity Play Client (C#) <-- authenticated IPC --> Java Game Gateway
  presentation, interaction,                   session ownership,
  inspection, audio/settings                   XMage translation,
                                               per-seat visibility,
                                               commands/events/lifecycle
                                                        |
                                                        v
                                                 Pinned XMage
```

1. Start with separate processes and a standalone Unity window. Investigate PyQt
   embedding only if it improves UX without lifecycle/platform problems.
2. Evaluate stdin/stdout versus authenticated loopback streaming. Pick the simplest
   transport supporting asynchronous events, cancellation, multiple seats,
   diagnostics and shutdown. Never bind publicly. Frame messages, cap sizes,
   authenticate ownership/seat and reject stale commands.
3. Explicitly version `GameSnapshot`, `GameEvent`, `LegalAction`, `ChoiceRequest`,
   `PlayerView` and `GameObject`. Share schemas and fixtures between C# and Java;
   do not manually maintain unrelated models.
4. Python may export an ephemeral validated manifest with seats, canonical deck
   snapshots and printing IDs. Java performs XMage resolution. Persistent decks
   remain native `DeckDocument`s; no second user-facing deck format.
5. Put a rendering projection between protocol and scenes. Display IDs stay stable
   only within their permitted viewer/incarnation lifetime. Never send unrestricted
   Java objects or raw XMage state.
6. Keep engine processing, asset decoding and database work off Unity's render thread.

## 3. Delivery tracks and dependency order

**Track A:** preserve Python as an executable reference; incrementally migrate
session, translation, visibility and lifecycle to Java.

**Track B:** develop Unity against deterministic viewer-filtered fixtures without
waiting for Track A. Converge in real local 1v1, then move gameplay testing to the
new client. Do not retire old code at transition start.

### Phase 0 — Architecture decision and build feasibility

Prove repeatable builds, tests, packaging and launch before migration investment.

- **P0.1 — Foundation:** pin an approved Unity LTS editor, URP initially, C# settings,
  repository structure, text serialization, tracked `.meta` files, package manifest
  and deterministic sample scenes. Exclude `Library/`, `Temp/` and built binaries.
- **P0.2 — Codex + CI:** inventory available official Unity automation/editor tooling.
  Prove compilation, batch tests, screenshots and Windows player builds in an
  authorized environment. Document license activation and secrets handling. Do not
  assume disposable GitHub runners can activate Unity Personal unattended.
- **P0.3 — Renderer:** real-artwork playmat with about 20, 70 and 200 objects,
  hover enlargement, selection, tapping and animated target lines. Record packaged
  frame times, latency, memory, startup and integrated-GPU performance. Use a small
  Qt Quick comparison only if the decision remains unresolved.
- **P0.4 — Licensing/distribution:** verify PyQt6, Unity, XMage, dependencies,
  card images and planned source/distribution compatibility; capture notices and
  redistributable artifacts. This is pending review, not a legal conclusion.

**Exit:** documented proceed/halt decision, repeatable licensed build path,
runnable packaged prototype, benchmarks and clear CI licensing answer. If this
fails, reassess Qt Quick before creating a large Unity codebase.

### Phase 1 — Freeze public protocol and launch boundary

- **P1.1 — Inventory:** extract every Python public contract/command, unsupported
  fields, seat observations, combat, commanders, printing identities, results and
  failures. Record pinned engine/adapter versions from current source.
- **P1.2 — Schemas/fixtures:** version commands, events, snapshots, errors,
  handshakes, seat tokens and acknowledgements. Generate sanitized golden fixtures
  from the adapter/tests. Distinguish submitted, confirmed, rejected and uncertain.
- **P1.3 — Manifest:** export required native deck data once, including commander,
  companion, selected printings, ownership and card identity. Validate before Java
  receives it; never quietly substitute unsupported cards.
- **P1.4 — Lifecycle:** define ownership of Unity, gateway, XMage, temporary workspace,
  startup failure, app close, crash, forced cleanup and orphan detection. Keep
  runtime pinning and update compatibility explicit.

**Exit:** Java/C# deserialize shared fixtures; dummy gateway/client exchange a
snapshot, legal action, rejection, result and shutdown without per-action Python. Preserve human/AI controller
configuration in the launch and gateway contracts.

### Phase 2 — Java gateway parity (Track A)

- **P2.1 — Startup:** reuse pinned validated server/bridge artifacts, consolidate
  working Java carefully, own only child processes and isolate runtime workspaces.
- **P2.2 — Viewer-safe state:** port normalization, metadata, opaque viewer
  incarnations, printing mappings, dynamic characteristics, commanders and filtering.
  Never give Unity a root all-seats session.
- **P2.3 — Decisions:** support all current action/choice families, action/decision
  IDs, stale rejection, mana sources, optional prompts, pending submissions,
  uncertainty and engine-confirmed outcomes.
- **P2.4 — Identity:** preserve single/double faces, tokens, copies, blink, control
  changes, artwork, commander/partner/background/companion and applicable error codes.
- **P2.5 — Acceptance:** compare Python/Java real-engine scenarios, including
  2–5-seat Commander, private reveals, trigger order, complex choices, combat and
  shutdown. Compare semantics/redacted transcripts, not nondeterministic IDs.

**Exit:** agreed parity matrix reproduces confirmed Python behavior with no known
privacy regression or duplicate rules. Retain Python until integration succeeds.
Do not claim every Magic card is validated.

### Phase 3 — Unity battlefield foundation (Track B)

- **P3.1 — Scenes:** seat-independent layout, 1v1 table/HUDs, hand fan, lands,
  creatures, stack, command zone, graveyard/exile and adaptive aspect ratios.
- **P3.2 — Printings:** cached actual artwork by printing ID/face, shared textures,
  bounded caches and concealed identities. Initial component rendering resolves
  nonstandard selections to compatible standard-frame printings of the same Oracle
  card and face, preferring cached artwork. Preserve selected printing identities
  and original showcase, full-art, borderless and unusual image sources; use
  authentic card-image fallbacks when reconstruction is unsupported.
- **P3.2a — Composable card rendering (planned, P0):** reusable standard-frame
  components with shared identity/resources, compact cropped battlefield cards and
  full hand/inspection cards. Render authoritative name, type, rules text, mana
  cost and P/T independently; support explicit mock projections while the gateway
  develops. Preserve selected/rendered printing and face distinctions. See the
  [story and acceptance criteria](play-composable-card-rendering.md). Depends on
  P3.2, precedes P3.3, and does not complete P0.3's benchmark gate.
- **P3.3 — Interaction:** use P3.2a's compact/full renderer for hover/zoom,
  select, drag, click-to-cast, tap rotation,
  targets, inspect, keyboard and contextual legal menus. Require engine tokens
  for every gameplay command; clicks never invent legality.
- **P3.4 — Decisions:** mulligans, targets/options, amounts, mana, mode/order and
  cancellation. Distinguish current/original characteristics and unknown fields.
- **P3.5 — Privacy/tests:** local seat switching destroys previous hand textures,
  tooltips, inspection, pending actions and scene references before showing the
  next viewer. Add deterministic scripted UI checks and screenshots.

**Exit:** scripted visual 1v1 changes turns, selects actions, handles an engine-style
choice and private handoff. Explicitly a fake-engine demo, not live gameplay.

### Phase 4 — First real end-to-end Unity + Java game

- **P4.1 — Launch:** choose saved human/AI decks in Manaforge, validate manifest, start owned
  engine/gateway and Unity, then return cleanly to Manaforge.
- **P4.2 — Exchange:** revisioned snapshots/events, exact legal actions and safe
  disconnect/timeouts/retries. Never blindly replay uncertain actions.
- **P4.3 — Vertical slice:** mulligan, draw, land, creature, choice, mana,
  stack/resolution, combat, attack/block, life and authoritative result.
- **P4.4 — Parity/privacy:** compare original adapter decisions/results; verify
  independent seats without hand leakage in source and packaged builds.

**Exit:** repeatable real-engine human-versus-XMage-AI 1v1 through Unity, validated results and cleanup.
An acknowledgement or concession-only demo does not prove natural completion.

### Phase 5 — Arena-like 1v1 UX

- **P5.1 — Battlefield:** natural scaling/spacing, large hand previews, readable
  opponent, unobtrusive zones, responsive resize and visual hierarchy. Polish the
  P3.2a card components rather than replacing their reusable architecture.
- **P5.2 — Events:** ordered viewer-safe engine-confirmed draw/cast/resolve/zone/
  tap/target/counter/damage/transform transitions. New authoritative state wins;
  animation never infers unconfirmed outcomes.
- **P5.3 — Combat:** clear attacker/blocker selection, target lines, confirmation,
  attack-all, assignments and damage. Keep individual decisions accessible.
- **P5.4 — Priority:** phase stops, temporary hold, full control and safe engine-
  permitted auto-pass. Never auto-select strategic targets, optional costs or
  modes; retain manual access when ambiguous.
- **P5.5 — Stack:** contextual view, inspect/resolve, target/trigger order and
  repetitive prompt consolidation only where rules permit.
- **P5.6 — Accessibility:** keyboard, reduced motion, color-independent cues,
  sound, adjustable zoom, useful empty/loading and failure/recovery states.

**Exit:** an Arena-familiar person completes normal 1v1 without instruction,
retains manual control and makes no illegal/unintended decisions due to presentation.

### Phase 6 — Complex display, stress and local Play alpha

- **P6.1 — Characteristics:** advanced characteristic handling, tokens/copies,
  attachments, transforms, commanders and complex permanents with exact artwork.
  Basic rendering of authoritative current characteristics, counters and damage
  belongs to P3.2a; this milestone extends its projection and components.
- **P6.2 — Dynamic text:** advanced authoritative-text correctness, complex layered
  effects and unusual-frame research. Basic authoritative dynamic text rendering
  belongs to P3.2a. Generic replacements cannot claim accuracy for every layout.
- **P6.3 — Crowds:** group equivalents while retaining IDs, expand for decisions,
  split diverging states and support large token/trigger counts.
- **P6.4 — Robustness:** integrated/low-end GPUs, 1366×768 through 4K, cache bounds,
  large scenes, restarts, interruptions and compatibility errors.
- **P6.5 — Release:** verify installer/runtime inclusion, updates, storage independence,
  offline startup, preserved data and opt-in/feature gating. Resolve notices and
  redistribution details.

**Exit:** real-deck end-to-end acceptance, complex-board benchmarks, accessibility
and hands-on UX approval. Only then retire Qt Play and remove Python from live
gameplay. Installed Play stays gated until review.

### Phase 7 — Private networked 1v1

- **P7.1 — Transport:** reuse versioned contracts over authenticated networking;
  do not expose local IPC unchanged. No public matchmaking or mandatory accounts.
- **P7.2 — Seats:** authorize connections/seats; send only permitted state, artwork
  references, events and decisions. Secure connections and cap sizes/rates.
- **P7.3 — Reconnect:** disconnect/rejoin/recovery/wait/host shutdown without
  private-state leakage or replaying uncertain commands.
- **P7.4 — Friends:** independent clients finish real-deck games with priority,
  combat, stack and disconnect scenarios.

**Exit:** reliable private host-authoritative remote 1v1 with rules/privacy intact.

### Phase 8 — Three-, four- and five-player Commander

- **P8.1 — Seats/priority:** generalize routing/selection with XMage legal order;
  hardcode neither two seats nor five as a protocol maximum.
- **P8.2 — Layout:** stable overview/compare/focus/inspect for two, three or four
  opponents; preserve local readability instead of shrinking everything uniformly.
- **P8.3 — Combat:** multiple defenders, one attacked player's blockers, multiple
  assignments and defender-specific views.
- **P8.4 — Commander:** engine-reported tax, damage per opponent, command zone,
  partner/background/companion, elimination and turn flow.
- **P8.5 — Acceptance:** multiplayer priority, privacy, elimination, copies, tokens,
  large stacks, reconnect and actual friend games.

**Exit:** real 3-, 4- and 5-seat Commander with readable layouts, legal interactions,
correct privacy and confirmed outcomes.

### Phase 9 — Optional expansions after multiplayer

Initial human-versus-XMage-AI play is a migration requirement. Optional later
expansions include enhanced AI and mixed-controller tables (controllers independent of seats),
history/replay/statistics/borrowing/precons, full-art/showcase/specialized frame
reconstruction, advanced shaders/environments/
audio, macOS/Linux installers/signing/notarization, spectators, flexible hosting,
persistence/recovery and shared playgroups.

## 4. Cross-cutting acceptance for each Codex story

1. Dedicated scoped feature branch; preserve a working reversible path.
2. Focused local tests/checks are allowed by owner clarification. Leave full suites
   to CI; prove build/license feasibility and report tests only with actual evidence.
3. Compare existing contracts/docs; duplicate neither XMage rules nor persistent decks.
4. Bind viewer-authorized gameplay to current session, revision/decision token
   and engine-provided action/option ID.
5. Protect concealed hands, looked-at cards, printing IDs and logs at both boundaries.
6. Engineer delivery, parsing, unknown fields, disconnect, cancellation and cleanup now.
7. Add appropriate deterministic fixtures, Java unit/integration, C# EditMode/
   PlayMode, packaged smoke and screenshot checks. Sanitize artifacts.
8. Owner cadence: review GitHub Actions every third commit without waiting
   between commits. Pending results may be assumed for continued development,
   but must be reported as unverified. Record exact commit/evidence and resolve
   known failures before gate acceptance. Never weaken assertions or gates silently.
9. Preserve data/engine pinning; no unreviewed engine upgrade, installer change
   or automatic public release. Follow repository prerelease/version rules.
10. Handoff: changes/files, CI link/status, demonstrated behavior, limitations and
    owner manual UX checks.

## 5. Critical go/no-go gates

| Gate | Required proof | Status |
| --- | --- | --- |
| G0 — Unity viable | Licensed repeatable builds and meaningful packaged graphics benchmark | Not demonstrated |
| G1 — Protocol stable | Shared Java/C# schemas; safe stale/invalid/private-data handling | Not demonstrated |
| G2 — Java parity | Confirmed Python behavior, complex choices and privacy reproduced | Not demonstrated |
| G3 — Unity 1v1 integrated | Real XMage actions, combat, stack and results through Unity | Not demonstrated |
| G4 — 1v1 UX accepted | Comfortable games, correct priority, responsive complex boards | Not demonstrated |
| G5 — Multiplayer ready | Reliable remote games without leaks/divergence | Not demonstrated |
| G6 — Commander ready | Real 3–5-seat Commander and crowded-board checks | Not demonstrated |

## Local progress — October 30, 2026

- P1.1 source inventory and drift check: `42096bf`; 64 focused adapter tests passed
  locally. CI and P1.2 shared schemas remain pending.
- P1.2 baseline increment: generated DTO JSON Schema and sanitized synthetic
  adapter fixtures, with 26 focused schema checks plus 64 adapter tests passing
  locally. A later increment adds generated Java/C# models and shared readers:
  14 positive round-trips and 12 negative rejections, with eight Unity EditMode
  checks passing. Authenticated transport and engine-derived golden transcripts
  remain pending; G1 is open.
- P0.1/P0.2 foundation: installed/licensed `6000.6.7f1`, URP `17.6.0`,
  six EditMode checks, one PlayMode scene check, Windows player build and a
  20-placeholder packaged camera screenshot demonstrated locally. See the
  [Unity foundation guide](../Mtg_Projects/mtg_play_unity/README.md).
- The installed editor is a current release, not LTS. Approved LTS selection,
  executed licensed CI, real artwork/interaction benchmarks and distribution
  review remain open. No G0/G1 completion is claimed.
- Owner clarified initial gameplay as human versus XMage AI, with five-player
  presentation in mind. This supersedes the original optional-AI sequencing.
  These are future design targets; the current increment is only P0 foundation
  and build/test feasibility, not live gameplay or multiplayer implementation.

- P1.3 foundation: immutable one-time native-deck export, separate private schema
  and Java-only DTOs; 29 focused Python checks and three positive/nine negative
  Java launch fixtures passed locally. [Launch boundary](play-launch-boundary.md)
  documents pending engine resolution and authenticated process delivery.

- P1.4 foundation: [owned-child lifecycle coordinator](play-launch-lifecycle.md),
  explicit readiness/deadlines, cancellation, reverse cleanup and blocked retry.
  47 focused new/existing lifecycle checks passed, including tiny real child
  processes. Authenticated delivery, OS containment and orphan recovery remain open.

## 6. First Codex batch

Run in parallel only where interfaces are fixed:

1. P0.1 + P0.2: Unity project and reproducible CI/build/licensing proof.
2. P1.1 + P1.2: verified Python contract inventory and sanitized golden fixtures.
3. P3.1: fixture-only Arena-style scene spike, reusable card prefabs, no engine dependency.

Do not start the bulk Java port or discard Qt until G0 and G1 are demonstrated.
Complete renderer/licensing evidence before declaring G0. After those gates,
run P2 and remaining P3 concurrently, integrate at P4, then devote P5/P6 to
comfortable real 1v1. This plan creates no build/license/benchmark/CI success evidence.

## 7. Existing documents and precedence

- [Product index](roadmap.md) retains product-wide phases. P0–P9 here are Play-specific.
- [Long-term Play epic](manaforge-play-epic.md) retains 2–5 seats, complex tokens,
  hidden information and playgroups. This roadmap supersedes Play rendering/adapter
  implementation approach, not the product vision or unrelated PyQt modules.
- [Historic Qt local delivery](play-local-game.md) and [AI/Focused View epic](play-ai-focused-view-epic.md)
  retain implementation history and regressions. Their AI-first/Qt delivery order
  is superseded. The owner subsequently confirmed human-versus-XMage-AI as the
  initial playable target; preserve its AI acceptance evidence and remaining gaps.
- [Python adapter](../Mtg_Projects/mtg_play/ADAPTER.md) and existing acceptance
  fixtures are initial behavioral truth for parity. Update runtime docs as Java
  actually replaces Python; proposed schemas do not establish parity.
- [Priority](play-priority-control.md) and [mulligan follow-up](play-mulligan-engine-followup.md)
  retain baseline behavior/evidence, without prescribing Unity implementation.
- [Architecture cleanup](architecture-cleanup-epic.md) and [product vision](long-term-product-epic.md)
  remain applicable outside this scoped migration.

**North star:** a friend chooses a saved Manaforge deck, starts Unity Play and
finishes Magic with Arena-like fluidity. Later the same client supports a four-player
Commander pod with native decks, XMage rules, accurate artwork/current state and
private information kept private.


### G1 local dummy-transport evidence — October 30, 2026

An [owned Java↔Unity EditMode fixture](../Mtg_Projects/mtg_play/protocol/dummy-exchange.md)
now exchanges private viewer bootstrap/authentication, mock snapshot/action,
stale/pending rejection, submitted ACK, explicit fixture-only result and clean
shutdown. Wrong-key and owner-EOF checks pass locally. No Python action relay,
XMage startup, packaged UI match or real result is involved. Forty focused
EditMode checks and four schema checks pass; licensed CI and final public body
validation remain pending. G0/G1 remain open and the bulk P2 port stays gated.


### G0 real-artwork preparation — October 30, 2026

An [offline fixture exporter](play-artwork-fixtures.md) now reuses the installed
Core catalog/artwork cache to prepare authentic, bounded raw RGBA resources.
The local seven-card bundle contains 21 assets (about 46 MiB), with selected
identities preserved and standard alternatives available. Twenty-seven focused
catalog/export checks pass. This removes image decoding from the planned Unity
rendering path but does not yet connect a player renderer or establish GPU,
startup, interaction or 20/70/200 performance evidence. G0 remains open.


### G0 packaged artwork fixture — October 30, 2026

The [offline artwork fixture](play-artwork-fixtures.md) now loads through a strict
worker boundary and renders in the packaged Unity player. Visually inspected
20/70/200-object captures use seven shared textures (~15.3 MiB raw pixels), with
compact cards and full inspection. Sixty-seven EditMode checks and three PlayMode
checks pass locally. This is a public printed-mock renderer, not live gameplay or
a measured performance benchmark. G0 remains open for interaction/performance,
integrated GPU, licensed CI, approved LTS and distribution review; G1 remains
open and bulk P2 stays gated. Human-versus-AI and future five-seat support remain
the playable direction, not claims made by this fixture.


### G0 scripted measurement harness — October 30, 2026

The [packaged renderer harness](play-renderer-benchmarks.md) now exercises fixture
pointer selection, tap rotation and target-line animation at 20/70/200 objects.
It records five-second offscreen loop/CPU intervals, startup and externally sampled
process memory with raw artifacts. GPU counters were unavailable on this hidden
Direct3D 12 path; these intervals are not presented FPS or input latency. G0 stays
open for visible graphics/latency evidence and the other outstanding acceptance.


### G1 terminal error boundary — October 30, 2026

The [session-error contract](play-session-errors.md) now validates fixed terminal
failure categories in Java/C# and preserves pending command uncertainty while
refusing reconnect. An actual authenticated dummy process sends submitted ACK,
SESSION_FAILED and EOF without a game result. Eighty focused EditMode checks,
Java corpora and seven schema checks pass locally. Production error routing,
cleanup, licensed CI and the G1 freeze remain pending; P2 has not started.


### G1 receive history — October 30, 2026

The [bounded receive history](../Mtg_Projects/mtg_play/protocol/receive-history.md)
now drops identical data-message retries and rejects conflicting IDs, revision
rollback and capacity overflow in Java/C#. A result terminates new data admission;
events can share revisions. Ten shared sequences, mutation/concurrency checks and
a duplicated snapshot in the actual dummy exchange pass locally, within 86
focused EditMode and eight schema checks. Missing-event detection, recovery,
licensed Unity CI and real-engine emission parity remain open. G1 is not frozen.


### G1 bounded client receive inbox — October 30, 2026

A [client worker inbox](../Mtg_Projects/mtg_play/protocol/receive-inbox.md) now bounds
queued packet count/UTF-8 bytes and clears owned data/history on overflow,
validation failure or cancellation. Dequeue transfers explicit packet ownership;
normal input completion permits draining. Fifteen new checks plus the actual
Java-dummy handoff bring local focused EditMode validation to 101. Socket read
deadlines/cancellation, owner coordination, renderer projection and licensed CI
remain pending; G1 is not frozen and bulk P2 remains gated.


### G1 client socket-read deadlines — October 30, 2026

An [owned loopback frame reader](../Mtg_Projects/mtg_play/protocol/frame-read-deadlines.md)
now uses one monotonic budget for header/payload reads, observes cancellation and
closes on failure. Fifteen real socket checks and a sixth authenticated dummy
partial-frame timeout/cleanup case pass within 117 focused EditMode checks.
Product owner coordination, Java-side deadlines, write/handshake budgets and
licensed CI remain pending. G1 is not frozen; no bulk P2 port has begun.


### G1 Java socket-read deadline parity — October 30, 2026

Java now uses the matching [whole-frame loopback deadline](../Mtg_Projects/mtg_play/protocol/frame-read-deadlines.md)
for dummy authentication and commands, with cancellation/interruption and owned
socket closure. Sixteen Java loopback cases and a seventh authenticated Java↔C#
partial-frame scenario pass locally, within 118 focused EditMode checks. Earlier
protocol CI runs passed at the scheduled snapshot; new licensed Unity evidence,
write budgets, product coordinator and G0/G1 acceptance remain pending. Bulk P2
has not started; this is engine-independent transport work.


### G1 bounded C# frame writes — October 30, 2026

A [client write boundary](../Mtg_Projects/mtg_play/protocol/frame-write-deadlines.md)
now validates before sending, bounds socket progress and closes without retrying
uncertain chunks. The seven actual Java-dummy scenarios use it for normal client
sends. Twelve new socket/ownership checks bring focused local EditMode validation
to 130. Java write parity, product session coordination and licensed CI remain
pending. G1 is not frozen and bulk P2 remains gated.


### G1 Java frame-write parity — October 30, 2026

The [Java writer](../Mtg_Projects/mtg_play/protocol/frame-write-deadlines.md) now
bounds blocking output with an owned watchdog and closes uncertain failures
without retrying. Fourteen Java write checks include interruption, stale-watch
safety and scheduler cleanup. An eighth authenticated process scenario times out against a
non-reading client; all 131 focused EditMode checks pass locally. Product session
coordination, complete conversation budgets, licensed CI and G0/G1 acceptance
remain open. This is transport infrastructure, not the bulk P2 engine port.


### G1 first client session owner — October 30, 2026

The [C# client session channel](../Mtg_Projects/mtg_play/protocol/client-session-channel.md)
now coordinates perform-token admission, data/ACK/error routing, uncertainty,
bounded inbox cleanup and socket closure. Matching shutdown permits final packet
drain. Two authenticated process scenarios and 18 new focused checks pass within
151 local EditMode checks. Choice dispatch, complete session budgets, Java owner,
renderer projection, product containment and licensed CI remain open; G1 is not
frozen and the bulk P2 engine port has not started.


### G1 opaque choices and explicit controls — October 30, 2026

The [client owner](../Mtg_Projects/mtg_play/protocol/client-session-channel.md) now
admits offered option IDs plus explicitly permitted finish/cancel commands using
current viewer/revision/decision tokens. No prompt/card inference or automatic
choice occurs. Java/C# reject duplicate/empty option IDs. Three authenticated
choice fixtures, ten new owner checks, Java corpora and eight schema checks pass
within 164 local EditMode checks. Numeric/mana dispatch, actual engine choice
parity, product lifecycle and licensed CI remain open; G1 is not frozen.


### G1 numeric choice admission — October 30, 2026

The [client numeric boundary](../Mtg_Projects/mtg_play/protocol/numeric-choices.md)
now compares explicit number/amount entries with current engine-supplied bounds,
using exact mathematical totals without clamping or defaults. Twenty new owner
checks and two authenticated fixture modes pass within 186 local EditMode checks.
Mana-source admission, full session/lifecycle boundary work and licensed CI remain
open; G1 is not frozen and bulk P2 remains gated. Java/XMage choice behavior parity
is Phase 2/G2 acceptance after G0/G1.


### G1 viewer-scoped mana source admission — October 30, 2026

The [client mana path](../Mtg_Projects/mtg_play/protocol/mana-source-admission.md)
now binds source clicks to a current mana decision and viewer object incarnation.
It does not infer source usability or calculate payment. All seven specified wire
command families now have client admission coverage; fifteen new owner checks
and a sixteenth authenticated fixture case pass within 202 local EditMode checks.
Complete session budgets, Java owner, renderer projection, product lifecycle and
licensed CI remain open, so G1 is not frozen. Real Java/XMage behavior parity is
Phase 2/G2 after G0/G1; no bulk engine port has started.


### G1 bounded client authentication handoff — October 30, 2026

The [client handshake](../Mtg_Projects/mtg_play/protocol/client-handshake.md) now
checks trusted pins/viewer/nonces and proof under one total deadline before
returning the session owner. Sixteen new checks and two process cases pass within
220 local EditMode checks. This changes no rendered UI and needs no hands-on UI
verification. Product bootstrap, Java total authentication budgets, artifact/
process ownership and licensed CI remain open; G1 is not frozen.


### G1 bounded Java authentication boundary — October 30, 2026

The [gateway handshake](../Mtg_Projects/mtg_play/protocol/gateway-handshake.md)
now applies one monotonic deadline to proof receipt, validation and reply before
returning trusted viewer context. Sixteen Java authentication checks and 221
Unity EditMode checks pass locally, including 19 Java process scenarios. No UI
verification was needed. Private bootstrap, verified artifact/process ownership,
Java session owner, renderer handoff and licensed CI remain open. G0/G1 are not
complete; bulk P2 and real Java/XMage parity remain gated.


### G1 malformed authentication traffic coverage — October 30, 2026

Both authentication entry points now have six additional framing regression
cases: stalled headers/payloads, oversized length, invalid UTF-8, truncated payload
and pre-proof EOF. They assert failure/timeout and transport closure before any
session is returned. Local evidence is 227 Unity EditMode checks and 22 Java
handshake cases; no production behavior or rendered UI changed. G0/G1 and the
remaining bootstrap, ownership and licensed CI requirements remain open.


### G1 Java viewer command admission — October 30, 2026

The [Java command gate](../Mtg_Projects/mtg_play/protocol/gateway-command-admission.md) now binds all seven command families to an
authenticated viewer's current offered IDs, flags and numeric bounds. Newer events,
results and invalid observations revoke permissions; amount totals cannot wrap.
The dummy uses this gate without claiming real-engine legality or confirmation.
Thirty-seven new Java checks exercise the boundary. No UI changed. G0/G1 and
product ownership/dispatch/licensed CI requirements remain open.


### G1 Java admission and receipt ownership — October 30, 2026

The [Java viewer owner](../Mtg_Projects/mtg_play/protocol/gateway-session-boundary.md) now serializes offered-command admission and
one-time ledger reservation. Disconnect/fault revokes permissions while retaining
pending uncertainty; only trusted engine outcomes can resolve it. Thirty new Java
checks cover ownership, results, failures and concurrent duplicates. The normal
authenticated dummy uses this owner. No UI changed; full worker/process ownership,
bootstrap, engine dispatch, licensed CI and G0/G1 acceptance remain open.


### G1 Java reservation-to-enqueue handoff — October 30, 2026

The [dispatch handoff](../Mtg_Projects/mtg_play/protocol/gateway-dispatch-handoff.md) invokes a trusted enqueue once per new reservation,
under the viewer owner's monitor. Failures preserve uncertainty and revoke further
admission; duplicate/rejected requests never invoke it. Thirty-six new Java checks
cover failures, interruption, reentry and concurrent duplicates. The dummy uses a
synthetic recorder. No UI changed; engine worker/queue/process containment and
G0/G1 acceptance remain open. No bulk P2 port has started.


### P3.2a owner visual feedback revision — October 30, 2026

The [composable renderer](play-composable-card-rendering.md) now retains exact
printing surrounds, raises the artwork coverage, restores compact nameplates,
uses an offline symbol font for costs and gives P/T a beveled badge. Unknown costs
remain explicit; concealed views clear both frame/art references. This responds
to owner screenshots and remains pending a fresh hands-on visual review. No
live-game, G0/G1 or final renderer acceptance is claimed.


### P3.2a specialized-layout display gallery — October 30, 2026

Owner-expanded visual scope now includes planeswalkers, sagas, battles, tokens and
other layouts in a [25-entry gallery](play-layout-gallery.md). Specialized compact
and inspection views retain complete authentic images; normal-layout planeswalkers
are excluded from ordinary-frame reconstruction. A dropdown exposes all faces.
The supplied Downloads assets contain loyalty, chapter, defense and token parts;
curated component import and dynamic authoritative fields remain separate work.
This is printed-fixture presentation, not new gameplay support or G0/G1 acceptance.


### P3.2a cost and inline rules symbols — October 30, 2026

The [symbol component](play-card-symbol-rendering.md) centers actual glyph bounds
inside pips and formats supplied tap/untap/colorless/mana tokens inline in rules
text. Unknown/oversized notation retains a literal fallback. Concealment clears
inline runs; source text is never interpreted as gameplay or injected rich text.
The local Unity asset research handoff was reviewed for subsequent asset work.
The symbol review build still requires owner visual approval; G0/G1 stay open.


### P3.2a specialized minis follow-up — October 30, 2026

The [gallery](play-layout-gallery.md) now adds explicit compact profiles instead
of full-printing thumbnails for known families. Minis have art crops, independent
nameplates, kind indicators and supplied P/T/loyalty/defense. Split panes share one
texture; Battle, Room and plane orientations are supported. V2 printed-reference
fixture metadata remains separate from the game protocol and v1 remains readable.
Full specialized frames remain authentic images; no rules or chapter progression
are inferred. Owner visual review and G0/G1 acceptance remain open.


### G1 immutable viewer card slice — October 30, 2026

The [card projection](../Mtg_Projects/mtg_play/protocol/viewer-card-projection.md)
now turns validated snapshot/result messages into immutable, viewer-scoped card
inputs without retaining mutable wire objects, action authority or private
observations. Current characteristics and exact printing identity remain
independent; unknown and unsupported engine text is not replaced with printed
text. Concealed cards retain opaque routing only. This is a worker-side card
slice, not scene handoff, private cache lifecycle, live engine integration or full
G1 acceptance. G0/G1 remain open and bulk P2 remains gated. Owner accepted the
preceding visual foundation as sufficient to continue; no new UI review is
required for this nonvisual increment.

Local evidence: 313 Unity EditMode checks, including ten new projection checks
and existing Java protocol preflight, passed. CI review follows the scheduled
third-commit checkpoint; local evidence is not licensed Unity CI acceptance.


### G1/P3 viewer surface handoff — October 30, 2026

The [viewer surface owner](play-viewer-surface.md) now connects immutable card
projections to reusable CardViews under an epoch ticket and revision watermark.
It clears old inspection/cards before private-scope disposal, enforces a whole
empty frame on viewer switch, rejects late work and blocks callback reentry.
Current-face artwork is deliberately unavailable until an authorized asset
binding exists; no name/flip-based image inference or printed-rule substitution
occurs. The existing public gallery is unchanged. This component is tested on an
attached panel but not yet mounted in a live session; full scene/mailbox, private
asset loading, G0/G1 acceptance and P2 parity remain open.

Local evidence: 314 EditMode and 13 PlayMode checks passed. Lifecycle tests cover
private-resource cleanup order, a complete empty frame, retired disconnect and
inspection tickets, reentry, failure retention/retry and thread rejection. The
public fixture scene remains unchanged; production scene acceptance is pending.


### G1/P3 authorized single-face artwork

The [artwork boundary](play-viewer-artwork.md) now accepts exact, compatible
normal one-face catalog printings for visible, explicitly face-up projected
objects. Requests/completions are tied to the viewer ticket, applied revision,
watermark and current opaque object. Unknown/multi-face cases remain unavailable;
current names and transform flags do not choose another printing. Private GPU
scopes enforce budgets, share identical pixels only within an epoch and are
revoked after views clear. Current text/stats remain separate from printing art.
Local evidence: 315 EditMode checks and 19 graphics-enabled PlayMode checks passed,
including a real GPU readback with no skips. Core cache job integration, the UI
mailbox, scene mounting, general face contracts and G0/G1 acceptance remain open.
The public gallery is unchanged; no new owner UI verification is needed yet.


### G1/P3 bounded worker-to-UI handoff

The [render mailbox](play-render-mailbox.md) now coalesces complete projected
snapshots per viewer epoch and bounds queued private artwork by count/bytes.
Newer state retires obsolete completions; shutdown clears queued pixels. The UI
owner drains snapshots before a limited number of texture uploads without
bypassing its empty-frame barrier. Concurrent producers, watermarks, stale tickets,
queue overflow and shutdown are covered by local checks. Local evidence is 321
EditMode and 22 graphics-enabled PlayMode checks, including the GPU copy test;
no skips occurred in that graphics run. Active Core job scheduling and production
session mounting remain open, as do G0/G1 and P2 parity. No public scene changed.


### G1/P3 bounded artwork jobs

The [artwork coordinator](play-artwork-jobs.md) now runs asset providers off the
UI thread under per-epoch concurrency/queue limits. Viewer cleanup stops owned
jobs without waiting, signals cancellation on workers and disposes late or
mismatched results. Provider errors expose only fixed diagnostic codes. Fast
provider/concurrent admission coverage guards worker retirement against stranded
queues. Local evidence: 321 EditMode and 28 graphics-enabled PlayMode checks
passed, including Java preflight and the GPU copy test, with no graphics skips.
The concrete Core cache provider, provider deadlines/global retirement policy and
session-scene mounting remain open. No public UI changed; G0/G1 and P2 parity
acceptance are not claimed. CI review remains on the third-commit cadence.

### G1/P3 offline Core artwork provider

The [Core artwork provider](play-core-artwork-provider.md) now exports exact,
viewer-permitted cached printings once into a pinned launch sidecar and reads
verified raw pixels lazily on Unity workers. It reuses existing Core conversion,
reports unavailable/unsupported printings explicitly, and connects to the bounded
jobs/mailbox without a Python action loop. Initial support is standard normal
single-face artwork. Local evidence: 20 Python, 321 EditMode and 32 graphics-enabled
PlayMode checks passed. Product launch/scene mounting, specialized live face
contracts, G0/G1 and P2 parity remain open. The public UI is unchanged.

### G1/P3 bounded presentation pump

The [viewer presentation pump](play-presentation-pump.md) now joins mailbox drain,
bounded texture uploads and bounded artwork job admission in one per-update UI
entry point. It keeps queue backpressure without replaying accepted failed work
every frame, replaces pending requests on new snapshots, and preserves viewer
revocation and the empty-frame barrier. Local evidence: 321 EditMode and 37
graphics-enabled PlayMode checks passed with no graphics skips. This provides the host integration seam;
private bootstrap, actual scene mounting, G0/G1 and P2 parity remain open. The
public fixture is unchanged and needs no new owner UI review.

### G1 private viewer bootstrap contract

The [viewer bootstrap boundary](play-viewer-bootstrap.md) now shares a bounded
one-viewer schema between Python export and Unity parsing. It carries a loopback
endpoint, trusted expected context/pins, one seat-only key and optional artwork
pin, rejecting owner/deck fields. Key transfer is single-use and disposal revokes
unclaimed keys. Local evidence: 14 Python and 326 Unity EditMode checks passed.
Actual inherited delivery, fresh authentication challenge exchange, OS containment
and production mounting remain open; G0/G1 acceptance is not claimed. No UI changed.

### G1 private bootstrap pipe reader

The [Windows private pipe primitive](play-bootstrap-pipe.md) now receives one
bounded framed bootstrap and watches owner EOF without a blocking render-thread
read. Real anonymous-pipe checks cover fragments, truncation, deadlines,
cancellation and lifeline behavior; a Python child verifies inherited delivery.
Local evidence: 20 Python and 334 Unity EditMode checks passed. Product launcher
writing, packaged Unity stdin verification, UI shutdown wiring, fresh challenges
and OS containment remain open. No public UI changed; G0/G1 remain unaccepted.

### G1 launch-owned bootstrap writing

The [launch coordinator writer](play-owned-bootstrap-write.md) now supplies one
framed viewer payload to its owned client using bounded nonblocking writes.
Partial writes and pipe backpressure preserve cancellation and health checks;
failure invokes owned cleanup. A completed write is not client readiness. Local
evidence: 67 focused Python lifecycle/bootstrap checks passed, including real
children and stalled pipes. Packaged Unity startup, owner-loss UI wiring, fresh
challenges and OS containment remain open; G0/G1 acceptance is not claimed. No UI
changed. CI is reviewed at this third-commit checkpoint without awaiting runs.

### G1 packaged private-bootstrap diagnostic

The [headless packaged proof](play-packaged-bootstrap-proof.md) now connects the
owned Python writer to the actual Windows Unity player's inherited stdin. Four
cases passed: owner EOF, malformed payload, missing-frame timeout and non-fixture
context rejection. Both owned roots exited without forced termination in every
case; owner EOF reached main-thread diagnostic quit. The Windows build and 338
EditMode checks passed. This is a public-fixture diagnostic, not authenticated
gameplay or live private-view cleanup. Fresh challenges, real mounting, OS
containment and G0/G1 acceptance remain open. The public gallery is unchanged.

### G1 fresh viewer challenge exchange

The [challenge wrappers](../Mtg_Projects/mtg_play/protocol/viewer-challenges.md)
now generate independent gateway/client nonces on each connection before the
existing signed hello. Trusted bootstrap/template identity and pins are preserved;
unsigned peer context is never adopted. One budget covers the exchange and failed
attempts close their transport. Local evidence: 344 Unity EditMode checks, Java
shared-corpus/real-loopback checks and Python schema validation passed. A real
Java-process/C# test authenticates then runs the coordinated dummy session; wrong
keys are rejected. Real session mounting, installed artifact verification, OS
containment and G0/G1 remain open. No UI changed.

### G1/P3 viewer session receive bridge

The [session receiver](play-viewer-session-receiver.md) now connects a matching
authenticated channel to its viewer mailbox on the connection worker. Ordered
events/results/receipts are retained under explicit queue budgets, while only
render snapshots coalesce. Channel stop, owner cancellation, malformed data or
overflow revoke the captured mailbox; the UI pump clears the card surface and
private assets. A small result/receipt/uncertainty summary survives revocation.
Local evidence: 44 graphics-enabled PlayMode checks passed without skips. Real
scene mounting, choice/event UI projection, OS containment, installed-artifact
verification and G0/G1 remain open. The public gallery is unchanged.

### G1/P3 authenticated viewer session host

The [session host](play-viewer-session-host.md) joins trusted bootstrap, bounded
loopback connection, fresh authentication, ordered receive and UI pumping under
one viewer lifetime. Owner loss revokes the mailbox before the next UI update;
late attempts and retired hosts cannot populate or clear a replacement epoch.
The host waits for worker retirement and captures stop evidence before channel
disposal. Local evidence: 50 graphics-enabled PlayMode checks passed without skips.
This is attached-panel fixture integration; product mounting, artwork-sidecar
loading, full decision/event UI, idle policy, OS containment, installed-artifact
verification and G0/G1 acceptance remain open. No public gallery changes.

### G1/P3 packaged authenticated session fixture — owner UI review pending

The [explicit fixture scene](play-session-fixture.md) now joins inherited bootstrap,
real Java/C# authentication, receive projection, shared card views and owner-loss
cleanup in the packaged graphics player. The fixture shows one public and one
concealed object, with inspection but no gameplay commands or artwork sidecar.
Local evidence: 350 EditMode checks, Windows build and the packaged Java/player
proof passed; connected/cleared captures were inspected. Both roots exited 0
without force. Owner UI review is now required before treating this fixture UX
as accepted. Product launch, real engine play, full decisions, artwork binding,
OS containment and G0/G1 remain open. Existing gallery and Qt Play are preserved.

### G1/P3 authenticated host artwork lifetime

The [host sidecar integration](play-host-artwork-lifecycle.md) now opens matching
pinned Core artwork after peer authentication, mounts its bounded jobs on the UI
thread, and awaits their retirement before index/channel cleanup. Wrong manifest
context/pins fail closed; missing/corrupt pixels remain unavailable. Hidden objects
and replacement epochs retain their existing permission/cache boundaries. Local
evidence: 56 graphics-enabled PlayMode checks passed with no skips. The packaged
fixture layout and pending owner review are unchanged; product artwork wiring,
specialized faces, real gameplay, OS containment and G0/G1 remain open. CI is
checked at this third-commit checkpoint without waiting for unfinished runs.

### P3.4 immutable decision-data boundary

The [decision projection](play-viewer-decisions.md) now carries exact viewer-scoped
engine actions, choice tokens, prompts, flags and numeric constraints as immutable
data. It shares receive validation with cards, preserves unknown/null values and
adds no legality inference or default submission. The ordered receiver carries
typed decision frames on applied snapshots/results and releases references on
update disposal. Local evidence: 361 EditMode and 56 graphics-enabled PlayMode
checks passed without graphics skips. No new controls or visible fixture changes;
scoped UI binding, command submission, owner UI review and G0/G1 remain pending.

### P3.4 decision offer lifetime and availability

The [offer binding](play-viewer-decision-binding.md) now ties immutable decision
data to one receiver/snapshot identity and checks live channel context. Pending
commands disable submission without discarding the prompt. New state, newer
events, terminal/revoked scopes and matching stale rejections retire old offers;
late receipts for another decision do not clear fresh state. Local evidence: 362
EditMode and 65 graphics-enabled PlayMode checks passed with no graphics skips.
No outgoing dispatcher or new controls are enabled. The visible fixture and
pending owner UI review are unchanged; real-engine and G0/G1 acceptance remain open.

### P3.3/P3.4 bound outgoing commands

The [dispatcher](play-viewer-command-dispatch.md) accepts current opaque offers
and their exact engine-provided action/option objects. It reserves before worker
scheduling, revalidates at admission, writes off the UI thread and preserves
receipt versus confirmation versus uncertainty. Local evidence: 362 EditMode and
71 graphics-enabled PlayMode checks passed without skips, including concurrent
clicks, stale/replacement offers and owner cancellation. No new controls, numeric
or mana entry UI, live-engine acceptance or owner UI approval is claimed.

### P3.4 explicit numeric command dispatch

The [dispatcher](play-viewer-command-dispatch.md) now accepts explicit numbers
and ordered amount arrays through the same current-offer reservation. It copies
caller arrays, preserves signed integer limits, and delegates authoritative
constraint validation to the existing channel contract. Invalid input releases
the reservation without writing. Local evidence: 362 EditMode and 75 graphics
PlayMode checks passed with no skips. Numeric controls, mana-source references,
owner fixture UI review and real-engine/G0/G1 acceptance remain open.

### P3.4 viewer-bound mana-source submission

The [dispatcher](play-viewer-command-dispatch.md) accepts only exact source
references from the current mana decision frame. These contain opaque viewer
object routing, not eligibility or private identity. Engine validation remains
mandatory; no printed-text heuristics or automatic mana choices are introduced.
Old offers, incarnations and foreign same-ID references are refused before a
write. Local evidence: 364 EditMode and 79 graphics-enabled PlayMode checks passed
without skips, plus Java preflight. Mana UI, owner fixture review and live-engine
acceptance remain open. CI is next checked at 0.5.105 without waiting on active runs.

### P3.3/P3.4 explicit decision controls

The reusable [decision panel](play-viewer-decision-panel.md) displays prompts,
engine actions/options and flagged finish/cancel controls through the existing
bound dispatcher. Its display gate requires the current viewer's card snapshot
to be presented, including the empty-frame handoff barrier. Retained callbacks
revalidate their captured offer. All options remain reachable through bounded
pages; navigation never chooses. The component remains unmounted in product and
packaged session scenes pending owner visual review. Numeric/mana widgets,
ordered receipt UX and real-engine/G0/G1 acceptance remain open.

Local panel evidence: 364 EditMode and 84 graphics-enabled PlayMode checks passed
without skips, plus Java preflight. A synthetic pending-state capture is available
for owner review. The reusable component is not enabled in existing scenes.

### P3.4 explicit numeric entry controls

The [decision panel](play-viewer-decision-panel.md) adds initially blank number
and ordered amount fields, engine-provided bounds, deliberate submit, bounded
pagination and recoverable admission errors. Defaults are not selected. Existing
channel validation retains range/total/overflow authority; callbacks revalidate
the offer and input is cleared at replacement/revocation. Local evidence: 89
graphics-enabled PlayMode checks passed without skips, including five new real
loopback UI scenarios and a synthetic capture. Numeric visual acceptance, mana
widgets, ordered receipt UX, fixture mounting and real-engine gates remain open.

### P3.4 scoped gateway command feedback

The [decision panel](play-viewer-decision-panel.md) now distinguishes gateway
submitted/confirmed/rejected/uncertain status for its own current command. It
samples immutable records from the existing authenticated tracker, preserving
the separate ordered receive queue. It neither promotes a socket write to
confirmation nor applies an old command's receipt to a new offer. Revocation
clears feedback; uncertain commands remain blocked without retry. This leaves
product/fixture mounting, owner visual acceptance, recovery UI and engine gates open.

Local receipt-feedback evidence: Java preflight, 366 EditMode and 93 graphics
PlayMode checks passed without skips. Current CI status is not inferred; the next
scheduled check is 0.5.108. Existing scenes remain unchanged.

### P3.3/P3.4 explicit card-based mana input

The [decision panel](play-viewer-decision-panel.md) binds primary-card clicks and
keyboard submit on existing displayed CardViews to the exact current mana source
reference. It adds no renderer, inferred source eligibility or automatic payment.
Hidden identities stay hidden; pending input, old callbacks and non-mana decisions
cannot submit. View focus/tooltips/handlers are restored on replacement or disposal.
The component remains unmounted pending owner review and integration; engine,
fixture and product acceptance gates remain open.

Local mana-input evidence: 98 graphics-enabled PlayMode checks passed without
skips, including five new authenticated-loopback UI scenarios and a synthetic
capture. Hands-on review is pending. Relevant CI is checked at 0.5.108 without
waiting; no current CI success or engine acceptance is inferred from local tests.

### P2.3 safe automatic mana-payment foundation

The owner supplied a [payment story](play-safe-automatic-mana-payment-story.md).
The [isolated Java coordinator and pinned API investigation](play-payment-coordinator.md)
provide per-human-seat Auto/Manual/Full Control policy, conservative fallback,
serialized manual/automatic ownership and separately observed outcomes. No native
source solver or Unity payment rules were added. The live Java/XMage execution
port is absent, so production automation stays unmounted and all real-payment
acceptance remains open. This is the story's permitted isolated increment, not a
bulk P2 port, G2 parity claim or relaxation of G0/G1 gates.

Local coordinator evidence: 65 synthetic Java safety/lifecycle checks passed;
five native API classes were inspected after pin/hash verification. The protocol
CI workflow now includes these isolated checks. Real-engine payment, applied
native preferences and live gateway dispatch are explicitly not demonstrated.
Next scheduled CI review is 0.5.111; no current CI success is inferred.

### P2.3 native payment helper adapter and reference implementation

The [native helper probe and reference findings](play-payment-coordinator.md)
exercise unchanged pinned XMage objects and add a map-preserving selected-source
adapter around ManaUtil. The downloaded reference client receives payment plans
from its engine and submits original solution indices; it does not remove the need
for an XMage-backed planning/execution port. Local evidence: 65 coordinator and
31 native utility-object checks passed. Native map mutation, partial-cost testPay
semantics and generic-color fallback are documented as integration limits. No
production automation, source activation, real-game payment or UI acceptance is
claimed. Next scheduled CI review is 0.5.111.

### P2.3 shared manual/internal payment admission

The [gateway payment port](play-payment-coordinator.md) now reserves automatic
internal work through the same existing session boundary used by authenticated
client commands. Manual and internal work cannot both win admission; uncertainty,
replacement and disconnect do not silently release pending work. This adds no
payment policy to the command gate/ledger and creates no automatic client ACKs.
The real native XMage delegate remains absent, so production automation and P4.3
payment acceptance stay open. No Unity UI or shared wire schema changed.

Local shared-admission evidence: all focused Java protocol checks passed, including
110 new synthetic admission/port checks; the 65 coordinator and 31 pinned native
utility checks also passed. No actual source activation or payment completion is
claimed. Relevant CI is checked at 0.5.111 without waiting on unfinished runs.

### P2.3 native source-response executor reused by the reference bridge

The [native response executor](play-payment-coordinator.md) is now used by the
existing Java headless bridge's manual mana-source path. It consumes the exact
current callback decision before the unchanged XMage SDK call and preserves
Submitted versus Uncertain. The number scenario now requires two submitted
sources, tapped lands, mana spending and Walking Ballista resolution from real
engine state. This is native manual execution evidence, not automatic planning,
a naturally completed match or Unity/Java end-to-end acceptance. The production
automatic planner/controller remains absent; existing gates are not relaxed.

Final native manual-execution evidence: the strengthened number scenario passed
with two source submissions, two tapped lands, mana spent and 1/1 Ballista
resolution; all owned roots exited 0 without forced cleanup. Also passed: 65
coordinator, 77 source-response guard, 31 native utility and 105 focused Python
checks. No full application suite or new UI build ran. Next CI review is 0.5.114.
