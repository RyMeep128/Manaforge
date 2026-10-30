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
