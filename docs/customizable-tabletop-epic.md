# Customizable Tabletop, Modular HUD, and Shared Battlefield Organization

Status: implementation in progress; private drawer customization is enabled in the normal game menu by owner request. Hosted/full-game and owner acceptance remain incomplete.

## Implementation status (2026-11-11)

| Stories | Current state |
| --- | --- |
| CT-01–02 | HUD registry, capability boundaries, and legacy geometry extraction implemented. |
| CT-03 | Reusable container geometry and gesture infrastructure implemented. |
| CT-04 | Versioned named preset storage implemented. |
| CT-05A / CT-06 | Live editor for Priority, Actions, Zones, and Commander drawers, plus resolution recovery and session reset implemented; hosted Unity/full-game and owner acceptance incomplete. |
| CT-07–11 | Identity/session reducer, authenticated shared organization transport, native bridge, and opt-in normal owner integration implemented; exact-SHA native/full-game acceptance remains a release gate. |
| CT-12–14 | Flat-group rendering, selection and editing candidate implemented behind v2 opt-in; hosted/manual/native acceptance incomplete. See [shared rendering](play-shared-rendering.md). |
| CT-15–17 | Dynamic group drawers, reconnect reconstruction and join/leave policies remain unimplemented. |
| CT-18–22 | Automatic rules, visual stacks, land organization, and nested groups remain unimplemented. |
| CT-23–24 | Release acceptance and four-player shared-table gates remain incomplete. |

Normal games expose Customize Layout for the four existing drawer families.
This does not enable hand/battlefield repositioning or shared organization. Remaining acceptance is tracked in
[recovery and release evidence](play-layout-recovery.md#evidence-and-release-gate).
The story specifications below describe the full target, not completed acceptance.
See [CT-07A identity foundation](play-battlefield-identity.md) for its internal contracts and remaining gates.

Assessment date: 2026-11-10. Baseline: `b97f4914dba3847036fa6094603280f826a63aea`
plus the existing uncommitted working tree on `main`. In particular, Arena input,
menu, protocol, payment/session, styling, and CI changes were already present.
Revalidate these seams before implementation; this document does not claim those
changes have passed CI. Follow [development workflow](development-workflow.md).

## A. Vision and scope

Manaforge should enforce Magic's rules while letting players organize their table.
A player can keep mana rocks in a drawer, arrange a sacrifice engine together, and
move their hand and priority controls to comfortable locations. Opponents see the
same named battlefield structure and member ordering, with their own choice of
which drawers to expand. Five Forests remain five independently actionable lands.

This is one presentation architecture with three explicitly separate state owners:
rules state, shared organization, and private display preferences. Success means
organization survives ordinary game updates and reconnects without changing legal
actions, leaking private information, or making any permanent inaccessible.

### Delivery boundaries

| Release slice | Included | Exit gate |
| --- | --- | --- |
| Private layout preview | Registered HUD components, move/resize/dock, compatible drawer conversion, named presets and reset | Stories CT-01–06; default layout and normal game regressions pass |
| Foundational shared MVP | Flat named groups, selection and drag, shared normalized placement/order, group drawers, independent collapse, safe identity/lifecycle, two authenticated viewers, reconnect | CT-07–17 plus CT-23; cannot market a local prototype as shared multiplayer |
| Organization defaults | Durable preferences, deterministic rules, manual overrides, safe duplicate/land/token stacks | CT-18–21 plus renewed CT-23 evidence |
| Advanced tabletop | Nested groups, richer filters and four-player composition/acceptance | CT-22 and CT-24 plus renewed CT-23 evidence |

The shared MVP includes moving/removing individual members, deleting an empty or
populated group without deleting cards, creating a group from a dragged selection,
and converting a group to a drawer. Visual stack mode and automatic rules follow
the shared foundation. A private HUD preview can ship sooner, clearly labelled.
Core infrastructure must accommodate all HUD elements, but each component exposes
only compatible capabilities; priority/mandatory decisions cannot become unreachable.

Non-goals: new Magic zones, rules changes, bulk game actions inferred from a stack,
strategy automation, replacing XMage, rewriting card rendering, general cloud
profile sync, a public matchmaking service, host migration, engine process crash
recovery, and arbitrary scripts in grouping filters. Network deployment outside
the existing trusted local boundary requires a separate secure transport design;
opening the current loopback listener to the Internet is not this epic's solution.

## B. Repository architecture assessment

Paths below are relative to the repository. Runtime paths abbreviated `Runtime/`
refer to `Mtg_Projects/mtg_play_unity/Assets/Manaforge/Runtime/`.

| Evidence inspected | Current responsibility / limitation | Reuse or incremental change |
| --- | --- | --- |
| `Runtime/ArenaGameplayPresentation.cs` | Composes surface, player HUD, drawers, inspector, animation, targeting and input. `Layout()` directly sets hand, rows, stack toolbar, attachment offsets and drawer geometry. Opponent battlefield cards are combined into opponent rows; `OpponentId()` selects the first opponent for the hidden hand. | Keep composition and bindings; extract geometry/slot resolution behind an adapter. Add an organization renderer beside the legacy layout, not a replacement session host. |
| `Runtime/GameplayCardLayout.cs` | Row/hand paging, retained local hand order, attachment root traversal (bounded depth), land fan geometry. `BattlefieldGeometry` hardcodes a 280px rail, four rows and hand margin. `LandStacks` groups conservative visible equivalent lands, maximum two, including tapped state in identity. | Keep default geometry and paging as legacy strategy. Extract allocation and member access helpers. Existing two-land piles are geometry, not persistent groups or mixed-state stacks. |
| `Runtime/GameplayDrawer.cs` | Directional UI Toolkit shell with local `IsOpen`, focus restoration, attention, reduced motion, closed-subtree input suppression and disposal. Title is constructor-owned; no registry, move, resize, persistence or dynamic membership. | Compose shell primitives; add safe title binding and geometry hooks. Preserve `RefreshInput()` and resource lifetime behavior. Do not make drawer instances the shared state model. |
| `Runtime/GameplayPlayerHud.cs`, `GameplayPanelDrawers.cs` | Independent player/Commander views, local seat placement, format gating; spells/abilities attention opens mandatory choices, priority drawer wraps existing controls. | Register independent HUD components; retain decision and Commander bindings and attention policies. Split wrappers only as needed for slots. |
| `Runtime/Resources/GameplayTheme.uss`, `ArenaTable.uss`, `GameplayTheme.cs` | Reusable tokens/classes plus ID-based fixed positioning. Runtime inline geometry also overrides styles. | Keep theme; move placement ownership to one resolver. Scope editor/group styles; avoid competing inline and USS geometry. Existing `.selected` styling must not be repurposed for organization selection. |
| `Runtime/ViewerCardSurface.cs`, `ViewerCardProjection.cs`, `CardView.cs` | Viewer/ticket-owned admitted card views, inspection/artwork lifetime. `ObjectId` is current routing, `RenderId = PresentationId ?? ObjectId` provides presentation continuity; hidden objects clear characteristics. | Surface remains sole owner of card views/artwork. Resolve containers to placements/anchors; no second independently bound card model or speculative artwork. |
| `Runtime/ViewerBoardInput.cs`, `TargetingPresentation.cs`, `ViewerManaSourceInput.cs` | Board gestures capture exact current decision offer; 10px drag threshold, deliberate hand play/double-click, hardcoded drop rectangle. Targeting and mana use their own current-offer paths. Board activation currently requires an offered action. | Add explicit gesture arbitration; organization must work without priority or an offered action. Keep command admission and cancellation behavior unchanged. Replace hardcoded drop bounds with resolved regions. |
| `Runtime/GameplayAnimationCoordinator.cs`, `BattlefieldLinks.cs`, `GameplayOverlay.cs`, `ZoneBrowser.cs` | Motion/anchors, combat links, inspector and public-zone browsing. Browsing currently hides/repositions surface-owned cards. | Use one anchor service for collapsed/paged members, animations and links. Preserve public-zone browsing and inspection ownership; groups are never zone-browser data. |
| `Runtime/ViewerSessionHost.cs`, `ViewerSessionReceiver.cs`, `ViewerRenderMailbox.cs`, `ViewerCommandDispatcher.cs` | Worker receive/projection, UI-thread application, current presented offer/revision gating, cancellation and cleanup. Host opens one channel; termination cancels it. | Add separately versioned organization projection/mailbox; coherent pairing with rules snapshots. No network I/O in Unity callbacks. Reconnect requires new lifecycle work. |
| `Runtime/Protocol/ClientSessionChannel.cs`, `ReceiveMessages.cs`, Java `GatewayCommandGate.java` | Strict authenticated viewer/session/revision admission, offered command IDs, receipts, duplicate suppression and fail-closed protocol parsing. No generic extension channel or automatic reconnect/reset. Concede is a distinct session operation in current working tree. | Reuse trusted context, framing and ledger patterns. Explicitly extend schemas/admission; unknown organization messages cannot simply be injected into existing receive parsing. Keep organization receipts separate from unresolved game commands. |
| `Mtg_Projects/mtg_play/java/ManaforgeOpeningProjection.java` | Projects native state into viewer-safe objects/actions. Ordinary object references are newly opaque each projection; stack references have a separate map. `presentationReferences` maps native IDs only across currently admitted visible rows, then is replaced. Players also have viewer-local opaque IDs. | Introduce host-owned incarnation/seat maps before shared membership. Never equate cross-viewer IDs or persist current `object_id`. |
| Java `ManaforgeGameplaySession.java`, `ManaforgeAutomaticEngine.java`, `ManaforgeOpeningSession.java`, `ManaforgeUnityOpening.java` | Native engine progression, prompts, automatic payment integration, gateway submission/confirmation, authenticated Unity listener. Listener binds `127.0.0.1`, accepts one client for this path. | Host organization service alongside engine session; do not submit organization to native command/payment machinery. Multi-viewer fanout and independently resumed sessions are prerequisites, not existing capabilities. |
| Java `ManaforgeServerHost.java`, `ManaforgeGameMetadata.java`; `Mtg_Projects/mtg_play/live_game.py` | XMage server/metadata and Python launch/process/artwork ownership. | Extend owner lifetime and authenticated seat bootstrap incrementally. Python is not the replacement gameplay rules or synchronization engine; retired Qt gameplay is not a target. |
| `Runtime/PlayerDisplayControls.cs` | `PlayerPrefs` persistence for display mode/window dimensions. Other inspected gameplay views keep drawer/page/motion state in memory. | Preserve display keys; introduce a small versioned local layout/rules store. No existing named gameplay preset system was found in runtime. |
| Unity `Tests/EditMode`, `Tests/PlayMode`, protocol fixtures/Java consumers, `mtg_play/tests`, `.github/workflows/` | Existing seams for projections, channel/host, surface, targeting, drawers/layout and live acceptance. | Extend these seams rather than inventing a second test harness. Existing documentation contains historical local results; those are not current acceptance evidence. |

Useful existing test anchors: `GameplayDrawerLayoutTests`, `GameplayHudDrawerTests`,
`GameplayElementTests`, `ViewerCardProjectionTests`, `ViewerCardSurfaceTests`,
`ViewerSessionHostTests`, `TargetingTests`, and `ClientSessionChannelTests`.
Drawer layout tests already cover 1280×720, 1366×768, 1920×1080 and 2560×1440,
including dense multi-seat fixtures. Fixtures alone do not prove live multiplayer.

## C. Technical design and decisions

### C1. Ownership and interfaces

All names in this section are proposed, not claims of existing APIs.

| Domain | Authority and lifetime | Payload / interface |
| --- | --- | --- |
| Rules | XMage/native match owner | Current viewer projection: zones, characteristics, tapping, counters, attachments, combat, actions and decision tokens |
| Shared organization | Match-host `BattlefieldOrganizationService`, surviving viewer disconnect | Per-seat organization tree, group IDs/names/modes, membership/order, normalized battlefield positions, organization revision; `Apply(actor, command, currentPublicBattlefield)` |
| Private layout | Local profile, outside match state | `HudLayoutPreset`, component placement/docking/sizing, local drawer state, camera/zoom and default rule preferences; `ILayoutPresetStore` |
| Unity projection | Viewer-scoped immutable data | `OrganizationProjection`, `OrganizationFrame`, current rules-to-member map; no native IDs exposed |
| View composition | Unity UI thread | `IHudComponentRegistry`, `ContainerShell`, `LayoutResolver`, `BattlefieldOrganizationRenderer`, `CardAnchorResolver`, `GestureRouter` |

`HudComponentDescriptor`: stable component ID, factory/binding adapter, supported
modes, minimum/maximum size, allowed docking edges/hosts, priority/attention policy
and default slot. Register hand, per-seat player information, Commander information,
priority, spells/abilities, library/graveyard/exile panel, battlefield viewport,
drawers and later components. Missing-format components keep dormant saved slots;
unknown future IDs are retained but not instantiated. No switch over every future
component in the editor. Actual game stack has its own descriptor, distinct from
a visual permanent stack.

Use shared shell primitives (header, content slot, focus, handle, resize grips,
motion, clamping), not a universal state superclass. A `HudContainerBinding` owns
private placement/preset behavior; a `BattlefieldContainerBinding` renders host
organization and sends intents. Neither owns cards or rules. Layout editor drag
and in-game organization drag share pointer mechanics but have different policies.
Reuse `GameplayDrawer` for focus/attention/animation rather than duplicating it.

### C2. Model invariants and permanent identity

Proposed host model:

```text
MatchOrganization { schemaVersion, matchEpoch, organizationRevision, seats[] }
SeatOrganization { seatId, roots[], groups[], membership[], rulesVersion }
Group { groupId, parentId?, name, mode: group|drawer|stack,
        orderKey, position: normalizedRect, provenance: manual|automatic }
Membership { permanentIncarnationId, parentGroupId?, orderKey,
             provenance, manualOverride: assigned|ungrouped|none }
```

The host mints an opaque permanent incarnation on battlefield entry, keyed
internally by native identity **and observed zone-entry generation**. Validate
generation against native zone-change metadata; native UUID stability alone is
insufficient. CT-07 must prove the adapter boundary distinguishes leave/reenter
even if intermediate snapshots are coalesced. If it cannot, add bounded native
lifecycle metadata before enabling membership persistence. Never match by name,
printing, array index, current command ID or viewer-local `presentation_id`.

Keep host native mappings private. Each viewer receives an opaque member handle
and its mapping to their currently admitted object reference; it need not be the
same handle another viewer sees. Group IDs are opaque match-scoped public IDs.
Use canonical authenticated seat IDs internally and viewer-safe seat mappings in
projections. This also avoids treating viewer-local player IDs as global owners.

Each live permanent has at most one organization parent; absent membership means
the default battlefield root. A group may contain cards and later child groups.
The tree cannot contain cycles, cross-seat parents or duplicate memberships.
Deleting a group reparents members/children to its parent in stable order; it never
issues a game action. Removing the last member preserves the empty named group.
Membership edits are atomic across the whole selected set.

| Native change | Required organization behavior |
| --- | --- |
| Tap, counters, damage, continuous effects, ability changes | Same member; update summaries from rules frame, never replace game object |
| Transform/flip/copy in place | Retain membership if incarnation persists; refresh visible characteristics/artwork through existing authorized path |
| Leave battlefield, token disappears | Remove membership and local selections; leave group intact; invalidate anchors and pending intents |
| Reenter/blink/replacement creates new permanent | New incarnation; use current entry rules, never recover stale manual membership by card name |
| Controller changes | Remove from old controller's organization atomically; new controller gets default/automatic placement; original owner gets no organization permission |
| Attachment changes | Rules relationships remain authoritative; group membership cannot detach or attach anything; provide attachment badge/links/browser across groups |
| Face-down or visibility revocation | Revoke identity-derived automatic labels/buckets and member handles as required; use generic public representation only, preserving no private identity continuity |

MVP may restrict face-down/concealed members to generic default placement if the
projection cannot prove safe public continuity. They must remain accessible through
current offered actions and generic inspection. Mixed-state stacks never combine
native objects; summaries show total, tapped/untapped/unknown and exceptional
counter/attachment/damage indicators. They never imply shared abilities or legality.
Different creatures may share a manually named visual stack, but selecting or
activating always resolves one current permanent and offered action.

### C3. Layout, input and access

Persist normalized anchor rectangles plus logical-unit minimums and docking data,
not raw desktop pixels. LayoutResolver applies viewport safe areas, UI scale,
reserved mandatory controls, min/max sizes and deterministic overflow into scroll
or paging. Shared positions live in the owning seat's normalized battlefield
space; opponents project that space into their own viewport. Personal HUD moves
never alter shared group coordinates. Avoid overlap where practical but allow
intentional overlap with a reachable header and a reset/recovery action.

Docking supports edges and compatible registered hosts using an acyclic dock graph.
Reject cycles and incompatible modes; deterministic order resolves competing slots.
The legacy arrangement remains the default strategy and a selectable preset.
Customize Layout in Escape Menu opens an explicit private HUD edit layer with
Apply/Cancel/Restore Default. Gameplay continues; show new mandatory prompts,
interrupt edits for required decisions, and prevent edit clicks from sending game
commands. Editing does not pause XMage or silently change yield settings.

In-game grouping never requires HUD edit mode. Shift-click toggles organization
selection of controlled battlefield permanents; a selection toolbar/context action
provides Move to group/New group/Ungroup and a visible drag handle. Dragging that
handle onto an existing group moves members; dropping onto an empty battlefield
target offers a named new group. Group headers move groups. Unmodified card clicks,
double-clicks and existing game drag paths keep their present behavior.

GestureRouter precedence: blocking modal/reveal -> current targeting/mana/combat
choice -> explicit HUD edit -> explicit organization handle/Shift-selection ->
existing board action -> inspection. During active game-selection decisions,
Shift does not steal a target; organization controls communicate temporary
unavailability. Selection during ordinary waiting/no priority remains allowed.
Revalidate organization rights at commit; decision changes cancel game gestures;
visibility/controller changes cancel affected organization gestures. Escape closes
the innermost gesture/editor before menu handling. Capture loss, menu, disconnect,
and view disposal release every pointer and ghost.

Collapse is private per `(profile, matchEpoch, groupId)` and is not broadcast.
Every container exposes member list/search and keyboard traversal with paging.
When the engine offers a member in a collapsed group, show attention and a local
temporary member chooser/reveal. Choosing resolves the current viewer object and
uses existing decision methods. Opponents can inspect public members while keeping
their own drawer collapsed. Never tap/target the top card as a proxy for all members.
CardAnchorResolver supplies real card, container-header or member-chooser anchors
with explicit anchor kind; combat/target/motion overlays must not invent endpoints
for hidden objects. Show collapsed combat participation counts and accessible links.

### C4. Shared protocol and authority

Decision: Java match host owns organization as a sidecar to the native game,
serialized against authoritative lifecycle updates. Do not put it into XMage zones
or Python launch configuration. All peers, including the hosting player's UI,
submit validated intents. The actor comes from authenticated connection context,
never a writable `owner_id`. Organization is independent of priority ownership.

The existing one-client loopback path is not a multiplayer organization service.
CT-10 adds a match-lifetime coordinator with multiple authenticated viewer channels
and canonical seat mapping. CT-11 adds bounded fanout/projection. Initially prove
two viewers over trusted local channels to the same native match. Four-seat Unity
composition and remote deployment are separate gates; underlying XMage multiplayer
does not demonstrate those gateway capabilities.

Proposed wire additions (exact schema work belongs to CT-09):

```text
organization_command { matchEpoch, commandId, expectedOrganizationRevision,
                       basisGameRevision, operation, payload }
organization_receipt { commandId, outcome: applied|rejected,
                       organizationRevision, reasonCode? }
organization_snapshot { matchEpoch, organizationRevision,
                        basisGameRevision, viewerScopedSeatsAndMembers }
```

Operations: create/rename/delete group, move members, move group, set mode/order;
later rule evaluation and nesting. Organization has a separate receipt ledger and
revision stream; its messages do not revoke decision tokens, hold the engine's
single pending action, or advance game revision. Game snapshot changes still
invalidate game offers exactly as today. Serialize transport writes through the
existing owner to avoid interleaved frames, with bounded queues and game traffic
priority. Never wait for an opponent to acknowledge organization before proceeding.

For MVP broadcast bounded full organization snapshots after accepted edits and
rules reconciliation, rather than inventing a second delta replay engine. Each
snapshot is viewer-filtered and paired with the rules basis it needs. Unity buffers
a future-basis frame until matching/newer compatible rules state; if older, reconcile
against current admitted incarnations or request fresh snapshot, never resurrect
removed members. Pairing is required even when current game revision does not change.
Coalesce drag previews locally and send final drops only. Later deltas must preserve
equivalent full-snapshot reconstruction and gap recovery.

Host validation: actor controls every affected permanent and owns affected groups;
all members are current battlefield incarnations; expected organization revision
matches; basis references resolve to current incarnations; structure/limits are
valid. Reject entire batch on stale member/control/parent; return a fresh snapshot.
Duplicate command IDs return their recorded receipt without applying twice; reuse
with a different payload is rejected. No automatic game-command retry. Proposed
initial limits: 128 groups/seat, 4096 members bounded also by rules projection,
64 Unicode scalar values/name, 256 members/edit, nesting depth 4 later. Validate
finite normalized coordinates, payload/frame budget, names as plain text, and
rate limits. CT-09 measures encoded size and tightens limits to existing framing.

Do not broadcast native IDs, private characteristics, default rule predicates, hand
membership, private deck categories or hidden-card history. Evaluate automatic
rules using only characteristics publicly authorized for the affected member.
Public names are deliberate player speech, displayed as plain text; automatic
names must never incorporate private identity. Knowledge revocation removes derived
automatic metadata, not merely card artwork. Logs/evidence must be sanitized.

Reconnect is new work: retain sidecar state for match lifetime independently of
viewer socket; reauthenticate the seat, retire old ticket/credentials, clear private
views, obtain fresh rules plus organization snapshots and member mappings. Uncertain
organization command resolution uses retained command ID receipts or full snapshot;
unknown receipts require explicit reconciliation, not blind replay. No game command
is retried by this system. A replaced connection cannot keep modifying the seat.
Match epoch prevents replay across games. New authorized viewers receive current
filtered snapshots; transport disconnect does not imply concession or remove cards.
Engine elimination reconciles current battlefield and permissions; retained empty
group headers may remain read-only until match end. No midgame seat takeover or
spectator private access is implied. Host process loss ends this recovery guarantee.

### C5. Persistence and automatic rules

Store versioned JSON under `Application.persistentDataPath` in a profile namespace:
named HUD presets, active preset ID and default organization rules separately.
Write atomically via temporary file/replace with last-good backup. Validate schema,
limits and dock graph; migrate known versions, preserve unsupported files and load
safe defaults on corruption/newer schema. UI reports fallback and permits reset.
Never save current member/native IDs into between-game presets. Match organization
stays on host; local collapse/session overrides expire at match end. PlayerPrefs
display settings retain their existing ownership. Cloud sync is not required.

Rules are a constrained declarative list, not scripts: stable rule ID, enabled,
explicit priority/order, public predicate, output group template/mode and stacking
policy. Save private defaults between games; copy into a match override with clear
Reset to defaults / Save as defaults actions. Host receives only validated rules
needed to produce the owner's public organization, never broadcasts the rule list.

Deterministic precedence: explicit manual membership or explicit manual ungrouped
override -> first matching enabled rule ordered by priority then stable rule ID ->
default root. A permanent gets one parent. Rule edits/characteristic changes affect
automatic assignments only; explicit Reapply may clear chosen manual overrides
after explaining the scope. Sort equal candidates by host incarnation sequence,
never viewer array iteration or localized text. Persist generated template IDs so
re-evaluation updates existing automatic groups instead of creating duplicates.

Land options: none, identical, all lands, mana capability, custom rules. Duplicate
options: never, identical public cards, identical tokens. Precedence between land
and generic duplicate rules is explicit in the ordered rules list, with a UI preview.
Type predicates support artifacts, enchantments, creatures, lands and tokens;
multi-type cards use the same first-match rule. Exact duplicates use public canonical
characteristics/token descriptors, not artwork identity alone. Conservative policy
can split exceptional members without discarding their parent group/manual intent.

Mana capability is not color identity or printed-text parsing. Existing projection
does not provide a dedicated canonical mana-production capability set. CT-21 must
add an engine-derived public, conditional/unknown-aware summary or disable that
option as unavailable. Group by equal canonical sets (including colorless);
conditional/unsupported producers go to Unknown, not a guessed color bucket.
These categories never authorize payment; existing native automatic mana search
and manual-source admission continue unchanged.

## D. Ordered implementation stories

Order is review order; dependency lists permit independent private HUD work. S =
roughly 1–2 focused engineering days, M = 3–5; these are sizing guides excluding CI
and owner review. Split further if a story crosses both transport and rendering
implementation. Each story has its own narrow mergeable contract.

Global definition of done (GDoD), applicable to **every** story: implement only its
scope on `main`, preserve unrelated work, document interfaces/limits and rollback,
add the listed meaningful coverage through GitHub Actions, record exact-SHA evidence
and unresolved acceptance, and satisfy its acceptance criteria. For Unity changes,
also run `./tools/unity-play.ps1 -Mode Build` locally and report failures; CI is not
a substitute. Keep alpha versioning; increment patch before a requested commit,
without creating a tag/release. No local test suites. A blocked check is not a pass.

### CT-01 — Establish compatibility seams and evidence baseline (MVP, S / medium risk)

- **Problem:** Current layout, input and in-flight changes obscure regression boundaries.
- **Behavior:** Default game remains identical; new capabilities initially disabled.
- **Approach/modules:** Document public seams in Arena, surface, host, targeting and menu; introduce independent private-layout/shared-organization/stack/rules flags with legacy defaults. Capture existing supported gameplay and fixture cases.
- **Dependencies:** None; reconcile against current working tree before editing.
- **Acceptance:** Flags off select existing composition; missing server capability hides shared controls; no game command or version negotiation changes.
- **Tests:** Existing drawer, surface, targeting, menu and live-game CI baseline; report inherited failures separately.
- **DoD:** GDoD plus baseline evidence inventory and explicit rollback switch.

### CT-02 — Register HUD components and extract layout slots (MVP, M / medium)

- **Problem:** Arena owns hardcoded placement for independent components.
- **Behavior:** Default table retains all existing HUD components and attention behavior.
- **Approach/modules:** `IHudComponentRegistry`, descriptors and `LegacyLayoutStrategy`; adapt Arena, PlayerHud, panel drawers, hand, stack and zone panel into slots without moving surface ownership.
- **Dependencies:** CT-01.
- **Acceptance:** All components in C1 have stable descriptors or explicit read-only adapters; a fixture component registers without editing the layout editor; default geometry/format gating unchanged.
- **Tests:** Descriptor capabilities/uniqueness, register/unregister disposal and legacy screenshot/layout assertions.
- **DoD:** GDoD plus documented extension example.

### CT-03 — Shared container shell and geometry resolver (MVP, M / medium)

- **Problem:** Drag/resize/docking could be reimplemented per view.
- **Behavior:** Compatible panels move, resize and dock in a fixture workspace.
- **Approach/modules:** Compose `ContainerShell` with GameplayDrawer; normalized geometry, min/max sizes, dock graph, drop regions and pointer capture helper. Update scoped USS rather than broad visual rewrite.
- **Dependencies:** CT-02.
- **Acceptance:** Edge/container docking, reorder, undock and compatible drawer conversion work; cycles/NaN rejected; closed content cannot intercept input; unsupported capabilities are disabled.
- **Tests:** Geometry/dock reducer cases and PlayMode capture loss, nested focus, resize clamping and reduced-motion tests.
- **DoD:** GDoD plus reusable shell independent of organization and game commands.

### CT-04 — Versioned named layout preset storage (MVP, S / medium)

- **Problem:** Runtime-only geometry cannot survive restart.
- **Behavior:** Save/load/rename/delete named presets and restore built-in default.
- **Approach/modules:** `ILayoutPresetStore`, schema/migration/backup validation; persistentDataPath profile storage, descriptor-based defaults.
- **Dependencies:** CT-02–03.
- **Acceptance:** Atomic failure retains last good file; unknown components survive round-trip; corrupt/newer files safely fall back; default cannot be destroyed; no session/card IDs serialized.
- **Tests:** Filesystem integration for round-trip, interrupted write, migration, corruption, invalid dock graph and name conflicts in hosted Unity checks.
- **DoD:** GDoD plus documented file format and recovery behavior.

### CT-05 — Escape Menu layout editor (MVP, M / high)

- **Problem:** Players cannot customize the actual live HUD safely.
- **Behavior:** Customize Layout exposes handles, docking, resizing, drawer conversion/reorder, Apply/Cancel and Restore Default.
- **Approach/modules:** Menu extension, `HudLayoutEditor`, slot bindings and GestureRouter edit policy; use current working-tree menu lifecycle rather than replacing concession/options.
- **Dependencies:** CT-03–04.
- **Acceptance:** Hand, player/Commander overlays, priority, actions, zones and battlefield viewport adapt according to descriptor capabilities; Cancel restores prior layout; mandatory choices remain accessible; editor clicks never cast/tap/concede.
- **Tests:** PlayMode input isolation, required-prompt interruption, Escape precedence, menu/concession regression and restart persistence.
- **DoD:** GDoD plus private-layout preview owner walkthrough.

### CT-06 — Resolution recovery and default compatibility (MVP, S / medium)

Implementation and outstanding acceptance: [recovery guide](play-layout-recovery.md). Production enablement remains gated.

- **Problem:** Saved layouts can strand controls after display changes.
- **Behavior:** Presets adapt to aspect ratio/window size; recovery/reset is always reachable.
- **Approach/modules:** LayoutResolver safe area/UI-scale policy, overflow paging, PlayerDisplayControls resize integration and default fixture comparisons.
- **Dependencies:** CT-05.
- **Acceptance:** Test desktop sizes plus 1024×768 and 3440×1440; mandatory controls and drawer headers reachable; resizing mid-drag cancels or safely rebases; format changes keep dormant slots.
- **Tests:** Geometry properties, screenshot/keyboard checks at each size and fullscreen/window toggles.
- **DoD:** GDoD plus supported minimum viewport and documented fallback below it.

### CT-07 — Host permanent incarnation and canonical seat mapping (MVP, M / high)

- **Problem:** Current viewer IDs rotate or differ across viewers.
- **Behavior:** Group membership can follow the same permanent across ordinary updates safely.
- **Approach/modules:** Java projection/session/metadata identity registry, viewer-safe handle mapping; minimal optional protocol identity slice and matched validators/generated DTOs where needed.
- **Dependencies:** CT-01.
- **Acceptance:** Two viewers map one native incarnation independently; taps/transform retain it, blink/leave-reenter/token recreation do not; control changes preserve incarnation but change organization rights; hidden identity cannot be correlated via handles.
- **Tests:** Native lifecycle integration, skipped intermediate snapshots, reused native ID, face-down transitions and negative projection fixtures.
- **DoD:** GDoD plus evidence of native zone-entry generation; shared persistence stays disabled if unproven.

### CT-08 — Pure flat organization reducer and reconciliation (MVP, M / medium)

- **Problem:** Groups need invariants independent of Unity and networking.
- **Behavior:** Create/rename/delete/reposition groups; move/remove/reorder members while preserving empty groups.
- **Approach/modules:** Java `BattlefieldOrganizationService` model/reducer and small C# immutable projection model; transaction validation and lifecycle reconcile against CT-07 registry.
- **Dependencies:** CT-07.
- **Acceptance:** One parent/member, atomic batch edits, stable order, delete reparents without game actions; control/zone cleanup is atomic; root remains available.
- **Tests:** Reducer/property cases for every operation, stale members, duplicate edits, ownership, empty groups and lifecycle table C2.
- **DoD:** GDoD plus serialized invariants and deterministic fixture corpus.

### CT-09 — Explicit organization wire contract (MVP, S / high)

- **Problem:** Strict existing parsers cannot accept ad hoc sidecar messages.
- **Behavior:** Compatible clients advertise shared-organization support; old pairs retain the default table.
- **Approach/modules:** Protocol schema, generator source, Java/C# DTOs, receive/admission routing and fixtures; document organization revision/receipt isolation and capability negotiation.
- **Dependencies:** CT-07–08.
- **Acceptance:** Reject unsupported mixed pairs cleanly; finite/bounded payloads, member mappings and basis revisions validated; organization does not authorize game commands or advance decision revision.
- **Tests:** Shared positive/negative corpus, generated-model drift, oversize/Unicode/cycle inputs and legacy handshake behavior.
- **DoD:** GDoD plus reviewed message inventory, measured frame limits and upgrade policy.

### CT-10 — Match-lifetime authenticated viewer coordinator (MVP prerequisite, M / high)

- **Problem:** The Unity gateway path currently serves one owned viewer connection.
- **Behavior:** Two authorized viewers can observe the same running match with isolated private views.
- **Approach/modules:** Extract match owner from per-viewer connection lifetime in Java UnityOpening/GameplaySession; seat-bound bootstrap and bounded channel management through existing Python ownership boundary.
- **Dependencies:** CT-07, CT-09.
- **Acceptance:** One native match owner, distinct authenticated seats/projections; second viewer cannot impersonate first; either disconnect does not shut down another viewer or imply concession; parent shutdown still cleans all workers.
- **Tests:** Actual multi-channel Java process tests and native two-seat integration; private-hand cross-viewer canary and owner cancellation.
- **DoD:** GDoD plus working local two-viewer session evidence, explicitly not remote-network readiness.

### CT-11 — Organization admission, receipts and fanout (MVP, M / high)

- **Problem:** Local edits must be authoritative and visible without blocking rules progression.
- **Behavior:** An owner's accepted group/name/membership/position changes appear to all viewers.
- **Approach/modules:** Host service dispatch, separate ledger/revision, validated owner-only edits, viewer filtering, bounded full-snapshot fanout and transport scheduling.
- **Dependencies:** CT-08–10.
- **Acceptance:** A can organize only A-controlled battlefield; B can inspect but edits reject; duplicates apply once; stale expected revision returns fresh state; slow B cannot block A's native decisions.
- **Tests:** Two clients, concurrent edits/lifecycle removal, reordered/duplicate deliveries, forged owner, payload reuse, rate limits and queue pressure.
- **DoD:** GDoD plus evidence organization traffic never changes native game state or game receipt admission.

### CT-12 — Coherent Unity organization receive and renderer (MVP, M / high)

- **Problem:** Group state must pair with changing viewer object references.
- **Behavior:** Flat named panels render public members with shared ordering/placement.
- **Approach/modules:** Organization projection/mailbox/host integration, `BattlefieldOrganizationRenderer`, seat-relative viewport and anchor resolver; keep card views surface-owned and legacy renderer selectable.
- **Dependencies:** CT-03, CT-11.
- **Acceptance:** Future-basis buffers, stale snapshots cannot resurrect members, organization-only revision triggers relayout; ungrouped cards retain root placement; multiple opponent roots are distinct rather than merged.
- **Tests:** Projection/mailbox ordering, object-ID rotation, rules-before/after-organization permutations, artwork updates, surface retirement and renderer toggling.
- **DoD:** GDoD plus two-viewer visual fixture and no duplicate card/artwork ownership.

### CT-13 — In-game organization multiselection and gesture routing (MVP, M / high)

- **Problem:** Grouping gestures can steal casting, combat or targeting input.
- **Behavior:** Shift-click controlled permanents, clear/toggle selection, drag selection handle or use keyboard/context move commands without HUD edit mode.
- **Approach/modules:** `OrganizationSelection`, GestureRouter integration with BoardInput/Targeting/ManaSourceInput; distinct selection CSS, dynamic resolved drop regions.
- **Dependencies:** CT-12.
- **Acceptance:** Selection works while waiting/no priority; explicit game-choice modes retain precedence; new decision/control/visibility changes cancel affected gestures; no organization click submits a game action.
- **Tests:** PlayMode synthetic pointer/key capture, multi-selection toggles, normal double-click cast, mana, combat, stale offers, menu and disconnect cancellation.
- **DoD:** GDoD plus interaction precedence documented and manually reviewed.

### CT-14 — Live group creation and editing UX (MVP, M / medium)

- **Problem:** A renderer alone does not let a player organize a battlefield.
- **Behavior:** Create/name/rename/delete groups, drag selected members to groups or empty-space new-group target, remove individual members and reposition/reorder groups.
- **Approach/modules:** Group header/context controls, commands via organization dispatcher, pending/error feedback; local previews commit only on host receipt.
- **Dependencies:** CT-11–13.
- **Acceptance:** All C2 flat operations available without edit mode; deleting populated group retains cards; rejection rolls back preview; empty group survives subsequent rules updates; opposing controls read-only.
- **Tests:** End-to-end two-viewer operation matrix, invalid drop/no-op, stale/control-change rejection, rapid repeated edits and keyboard equivalent.
- **DoD:** GDoD plus reproducible “Mana Rocks” scenario.

### CT-15 — Dynamic group drawers and independent collapse (MVP, M / high)

- **Problem:** Collapsed containers can hide required gameplay interactions.
- **Behavior:** Convert group to drawer and back; each viewer independently expands/collapses and inspects every public member.
- **Approach/modules:** Battlefield drawer binding, local collapse cache, title updates, member chooser/paging, CardAnchorResolver integration with targeting/combat/motion/inspection.
- **Dependencies:** CT-12–14.
- **Acceptance:** A collapse never changes B's view; target/activate/tap offered member while drawer remains logically collapsed via temporary chooser; all attachments accessible; closed subtree has no stray input; no hidden characteristics leak.
- **Tests:** Mixed tap states, required target in collapsed/paged group, offscreen/removed member, cross-group attachments, focus return and reduced motion.
- **DoD:** GDoD plus real engine targeting/manual mana and combat walkthrough from collapsed drawers.

### CT-16 — Reauthenticated reconnect and full reconstruction (MVP, M / high)

- **Problem:** Current host termination provides no viewer recovery.
- **Behavior:** Rejoining the same authorized seat reconstructs current rules and shared organization safely.
- **Approach/modules:** New viewer connection lifecycle, host-retained sidecar/receipts, fresh bootstrap/ticket, full rules/organization pair, command reconciliation and old-connection fencing.
- **Dependencies:** CT-10–12, CT-15.
- **Acceptance:** Disconnect during move before/after receipt yields one authoritative outcome; group IDs/membership survive viewer reconnect; credentials/old tickets retired; uncertain game actions never replay; host loss is reported, not fabricated recovery.
- **Tests:** Process integration disconnect points, stale epoch/credentials, overwritten connection, refreshed member map, delayed old packets and private resource cleanup.
- **DoD:** GDoD plus reconnect reconstruction evidence from running native match.

### CT-17 — Join, leave and elimination policies (MVP, S / high)

- **Problem:** Viewer presence and rules-seat lifetime differ.
- **Behavior:** A newly authorized viewer sees current public organization; disconnected/eliminated players cannot edit improperly.
- **Approach/modules:** Coordinator permissions and snapshot admission, elimination reconciliation, read-only headers and explicit connection status UI.
- **Dependencies:** CT-16.
- **Acceptance:** Transport leave retains match state; elimination uses native battlefield/control outcomes; joining viewer receives no stale private metadata; ended match freezes edits and disposes sidecar at owner cleanup.
- **Tests:** Join after multiple edits, disconnect without concession, elimination/control transfers, rejected spectator/foreign-seat edits and final cleanup.
- **DoD:** GDoD plus documented seat-presence policy; no unauthorized seat takeover feature.

### CT-18 — Persistent rule preferences and match overrides (defaults release, S / medium)

- **Problem:** Players would otherwise recreate preferences each game.
- **Behavior:** Edit organization defaults, preview precedence, temporarily override a match and explicitly save overrides as defaults.
- **Approach/modules:** Rule schema/store separate from HUD presets, options UI, private authenticated host rule installation and validation.
- **Dependencies:** CT-04, CT-11, CT-17.
- **Acceptance:** Restart keeps defaults; match overrides do not silently overwrite them; opponents receive results only; unsupported rules disabled with explanation.
- **Tests:** Store migration/corruption, profile separation, override reset and privacy-negative wire fixtures.
- **DoD:** GDoD plus rule editor precedence examples.

### CT-19 — Deterministic automatic assignment and manual overrides (defaults, M / high)

- **Problem:** Overlapping type rules and continuous changes could reshuffle manual work.
- **Behavior:** New public permanents enter matching groups; manual membership/ungrouped choices remain respected.
- **Approach/modules:** Host-only ordered rule reducer, stable generated templates and public predicates for card types/tokens; reconcile lifecycle with entry sequence ordering.
- **Dependencies:** CT-08, CT-18.
- **Acceptance:** Artifact creature matches first configured rule; manual override survives characteristic/rule changes; explicit reapply has bounded scope; hidden identities never affect grouping or automatic labels.
- **Tests:** Permutation determinism, overlapping rules, repeated snapshots, entry/control changes, face-down revocation and manual-ungrouped override.
- **DoD:** GDoD plus golden input/result corpus shared by protocol and renderer tests.

### CT-20 — Identity-preserving visual stacks (defaults, M / high)

- **Problem:** Existing conservative two-land fans do not offer configurable stacks.
- **Behavior:** Stack/unstack manual groups, display mixed-state summaries and choose any individual member; auto-stack identical cards/tokens or never stack.
- **Approach/modules:** Group stack mode, safe duplicate predicates, member ordering, summary renderer, chooser and anchor integration; retain legacy land strategy under fallback.
- **Dependencies:** CT-15, CT-19.
- **Acceptance:** Five Forests remain five references; tapping three leaves two untapped; counters/attachments/damage/sickness/effect differences remain inspectable; no bulk activation; magic stack remains distinct.
- **Tests:** Five-land native manual-source scenario; token variants, nonidentical effects, unstack order, summary unknowns, targeting buried members and attachment links.
- **DoD:** GDoD plus native payment/targeting regression evidence and stack accessibility review.

### CT-21 — Land capability grouping and custom arrangements (defaults, M / high)

- **Problem:** Mana capability cannot safely be guessed from current UI text.
- **Behavior:** Choose none/identical/all/capability/custom land organization; conditional producers show an explicit unknown category where necessary.
- **Approach/modules:** Public engine-derived capability projection with completeness, schema/fixtures and deterministic canonical-set rule; bounded custom declarative predicates.
- **Dependencies:** CT-19–20.
- **Acceptance:** Colorless/multicolor/conditional sources categorized without rules inference in Unity; no capability disables option; existing native automatic payment unchanged; custom manual arrangements survive entry of new lands.
- **Tests:** Native representative source corpus, unavailable metadata, privacy filtering, precedence with duplicate rules and automatic/manual payment suites.
- **DoD:** GDoD plus documented supported capability coverage and unknown fallback.

### CT-22 — Nested groups and extensible filters (advanced, M / high)

- **Problem:** Flat groups cannot represent a combo with subassemblies.
- **Behavior:** Nest/reparent compatible groups with breadcrumbs, bounded depth, predictable collapse and custom filters.
- **Approach/modules:** Extend reducer/tree validator, protocol fixtures, renderer traversal and rule registry; retain separate HUD dock graph.
- **Dependencies:** CT-17, CT-19–20.
- **Acceptance:** Depth/cycles/cross-seat parenting reject atomically; deleting parent reparents stably; buried target always reachable; recursive summaries do not double count; older clients decline unsupported capability.
- **Tests:** Tree/property cases, depth limits, cycle attempts, nested collapse/target access, rule/manual precedence and reconnect reconstruction.
- **DoD:** GDoD plus bounded-tree performance evidence and nesting UX walkthrough.

### CT-23 — MVP regression, accessibility and rollout gate (MVP; repeated per release, M / high)

- **Problem:** Foundation features could regress near-complete games despite fixture success.
- **Behavior:** Reliable default/custom game play with keyboard alternatives, readable counts, attention and recovery controls.
- **Approach/modules:** Existing hosted workflows/acceptance drivers, scenario fixtures, scoped USS polish, sanitized performance/evidence reports and operator documentation.
- **Dependencies:** CT-01–17 for shared MVP; CT-18–21/22 when enabling those flags.
- **Acceptance:** Section F matrix and manual scenarios pass for supported scope; stale/unauthorized/privacy cases reject; no unreachable controls; full saved-deck human-versus-AI game evidence includes automatic mana, casts, abilities, priority, combat, targets and Commander behavior.
- **Tests:** Hosted Python/Core, Java/protocol/native payment and licensed Unity checks; packaged acceptance and owner visual/interaction review. Compare same seeded scenario flags off/on where supported.
- **DoD:** GDoD plus explicit feature enablement decision with evidence links and any unsupported scope still gated.

### CT-24 — Four-player composition and shared-table acceptance (advanced, M / high)

- **Problem:** Current first-opponent hand and combined opponent rows are insufficient for Commander tables.
- **Behavior:** A/B/C/D see each player's distinct battlefield groups; each chooses local collapse and HUD arrangement.
- **Approach/modules:** Per-seat battlefield/hand composition, bounds/overflow rules, canonical seat fanout through CT-10 and multiplayer acceptance drivers.
- **Dependencies:** CT-17, CT-23; CT-22 only if enabling nested mode.
- **Acceptance:** Four native seats/viewers, correct public group ownership, only each viewer's own hand visible; independent collapse; control changes/elimination and one reconnect reconstruct correctly; default 1v1 still available.
- **Tests:** Four-client process/native integration, dense Unity scenes at all supported viewports, host queue stress and complete Commander gameplay regression.
- **DoD:** GDoD plus four-viewer evidence; do not claim remote Internet play without separate transport acceptance.

### Dependency summary

```text
01 -> 02 -> 03 -> 04 -> 05 -> 06                 private layout preview
01 -> 07 -> 08 -> 09 -> 10 -> 11 -> 12          authoritative shared foundation
03 ------------------------------> 12
12 -> 13 -> 14 -> 15 -> 16 -> 17 -> 23          shared MVP gate (also 01–06)
04,11,17 -> 18 -> 19 -> 20 -> 21 -> 23          defaults/stack release gate
17,19,20 -> 22 -> 23                            advanced nesting gate
17,23 -> 24                                    four-player gate
```

## E. Risks and decisions requiring evidence

| Risk | Consequence | Mitigation / gate |
| --- | --- | --- |
| Viewer-local/rotating object identity mistaken for permanent identity | Wrong card moved/targeted or membership lost every snapshot | CT-07 lifecycle registry; current object resolution only at action time; no name matching |
| Missed leave/reenter between snapshots | Old manual assignment attaches to a new game object | Native zone-generation proof before CT-08 persistence; snapshot comparison alone insufficient |
| Multiple competing gesture handlers | Shift/drag casts, pays or assigns attackers unexpectedly | Explicit router precedence, handles, current-offer cancellation and real gameplay regression |
| Organization stream invalidates decision tokens or waits on network | Priority/payment stalls and automatic play changes | Independent revision/ledger; game traffic priority; host never waits for organization ACKs |
| Current single-viewer gateway mistaken for multiplayer readiness | UI looks shared in fixtures but cannot support players | CT-10 prerequisite, real two-viewer MVP and CT-24 four-seat gate |
| Hidden state inferred from grouping, labels or stable handles | Opponent gains forbidden identity/history | Public-only predicates, viewer projection, handle revocation, privacy canaries and no private rule broadcast |
| Collapsed/paged stacks hide legal options | Player cannot finish a choice/pay/target | Member chooser, attention, keyboard access, current-option resolution, header anchors |
| Group logic fights attachment/control/native changes | Illegal-looking ownership and stale views | Atomic lifecycle reconciliation; presentation never changes native attachment or controller |
| Layout refactor becomes renderer rewrite | Full-game progress regresses | Descriptor adapters, legacy strategy, independent flags, one surface/artwork owner |
| Dense groups/fanout rebuilds every frame | Input latency, allocations and queue starvation | Versioned dirty layout, bounded snapshots, final-drop sends, queue coalescing and measured CT-23 budgets |
| Uncommitted implementation changes or stale historical docs | Plan targets obsolete seams or claims false acceptance | Reinspect on each story; evidence by exact committed SHA; preserve existing work |

Proposed performance gate: use the existing dense 96-permanent fixture plus a
4096-object protocol-limit stress fixture. Record layout/receive allocations and
frame times on a named reference machine; compare flags off/on. CT-01 records the
baseline and CT-23 sets/approves measured budgets before enablement. No unmeasured
frame-rate promise is made here. Stress overflow must remain bounded and interactive
through paging even if the full limit is not simultaneously drawn.

## F. Testing, manual acceptance and rollout

### Automated coverage by boundary

| Boundary | Required coverage | Existing execution home |
| --- | --- | --- |
| Host model | Create/delete/rename/move/reorder, atomic multiselect, empty-group survival, manual override, auto-rule overlap, stack/unstack, lifecycle/control reconciliation, nested cycles | Java checks and fixtures driven by `play-protocol.yml`; add sidecar corpus beside existing protocol Java tests |
| Identity/native adapter | Zone entry/reentry, transformations, disappearance, control, mixed tapped/counters/damage/attachments, conditional mana summary | Java native integration; `play-live-opening.yml`, `play-payment-native.yml`, packaged Unity acceptance where needed |
| Wire/security | Two/four viewer projections, ownership, replay/idempotency, stale bases, out-of-order frames, size limits, malformed coordinates, privacy canaries, version negotiation | Shared schema/generated-model fixtures and Java consumers; `play-protocol.yml`, Python `mtg_play/tests` via `tests.yml` |
| Reconnect | Before/after receipt drops, fresh identity maps, connection fencing, coherent rules/organization pair, no replay of game actions, join/leave/elimination | Multi-process Java/native scenarios plus `ViewerSessionHostTests`/receiver/channel tests in hosted Unity |
| UI models/storage | Geometry/dock graphs, default registry, presets/migrations/corruption, deterministic rule preview, scale/aspect handling | Unity EditMode via `unity-play.yml`; filesystem integration on hosted runner |
| UI interactions | Shift multiselect, handles/drop targets, gameplay gesture precedence, collapsed-member targeting/payment/inspection, keyboard/focus, drawer input suppression, animations and disposal | Unity PlayMode extending existing drawer/targeting/surface tests via `unity-play.yml` |
| Normal gameplay | Automatic/manual/full-control payment, priority/yields, spell and ability choices, stack resolution, attack/block/damage, Commander tax/damage, zones/reveals, menu/concession | Existing packaged native acceptance steps in `unity-play.yml`, native payment workflow and live-opening workflow; add full-game scenario coverage, do not substitute opening success |
| Launch/package | Profile storage writable in installed app, fresh/default profile, old configuration upgrade and lifecycle cleanup | `tests.yml` packaging when applicable, `play-preview.yml`, packaged Unity smoke and manual installed-build review |

Existing `unity-play.yml` includes EditMode/PlayMode, Windows build/screenshots,
real-engine payment cases, normal shuffled human-versus-AI play and current
working-tree concession acceptance. Workflow presence is not proof of success.
Any new native/organization scenario must be explicitly added to a hosted runner;
writing a test file alone does not satisfy its story. Do not run local suites.

### Reproducible manual Unity scenarios

Use a recorded build SHA, feature flag set, deck/fixture seed and viewport. Capture
sanitized screenshots/receipts and the actual pass/fail outcome. Fixture checks
validate UX; repeat native-dependent steps in a real engine match.

1. **Default and private layout:** Start a normal saved-deck game with flags off.
   Cast a mana-cost spell with automatic payment, resolve a choice, activate an
   ability, pass priority and complete combat. Enable private layout only; open
   Escape -> Customize Layout, move hand/player info, resize compatible panels,
   dock/reorder Priority and Zones, convert a compatible panel to drawer. Cancel
   once, then Apply and save “Compact”. Restart/load/reset; default behavior and
   Commander visibility still work. Incoming required choice interrupts safely.
2. **Mana Rocks shared MVP:** Connect A and B to the same native match (later C/D).
   Give A three public artifacts. Shift-select them, drag the selection handle to
   empty battlefield, name group “Mana Rocks”, move the group, rename it, remove
   one member and move it back. B sees identical structure/member order/position.
   Delete populated group: artifacts remain on battlefield; create an empty group
   and verify it survives several priority updates. B's attempted edit of A rejects.
3. **Independent drawer access:** Convert Mana Rocks to drawer. Collapse for A,
   expand for B; neither changes the other. From collapsed view choose a buried
   artifact's offered ability, then target a buried permanent. Verify attention,
   temporary chooser, exact submitted object, focus return and visible target link.
   Repeat using keyboard only and with a target on another paged group.
4. **Five Forests:** In stack-enabled native scenario, group five independently
   identified Forests. Manually select three mana sources; exactly three tap, two
   stay untapped and summary reads 3/2. Untap/change one member, unstack/reorder,
   verify five references remain. Run automatic-payment spell separately with no
   manual rescue and inspect native outcome; organization never chooses payment.
5. **Different creatures/attachments:** Put creatures with different counters,
   damage, effects and summoning status into a visual stack. Attach an Aura or
   Equipment across group boundaries. Inspect each, target a buried creature,
   declare only a legal offered attacker/blocker and verify links and assignment.
   Collapse its container during combat; participating members remain accessible.
6. **Lifecycle and private information:** Blink a manually assigned permanent,
   transform one in place, remove a token and transfer control. Check new incarnation
   entry placement, retained in-place transform membership, empty-group survival
   and new-controller permissions. Turn an eligible object face down/visibility
   restricted; B cannot recover prior identity through auto-group labels, handles,
   inspector or stale callbacks. A hidden hand card is never an organization member.
7. **Rules and overrides:** Configure artifact before creature rule; introduce an
   artifact creature and confirm first-match behavior. Manually ungroup it, change
   a rule and advance turns: override persists. Explicitly reapply to that member.
   Test never/identical-token/identical-land/all-land policies and conditional mana
   producer Unknown behavior; restart to check defaults versus match overrides.
8. **Reconnect/join:** Disconnect A once before and once after an organization
   receipt, while B continues. Reauthenticate A, compare authoritative structure,
   fresh references and local collapse policy. Late authorized viewer sees current
   filtered table. Old A connection cannot edit; a native game action pending at
   disconnect is not replayed. Test elimination separately from socket closure.
9. **Viewport/accessibility:** Repeat dense 96-permanent fixture at 1024×768,
   1280×720, 1366×768, 1920×1080, 2560×1440 and 3440×1440; resize mid-drag,
   toggle fullscreen and reduced motion. Tab to every header/required action;
   counts have text labels beyond color, selection differs from legal-target and
   combat emphasis, drawer focus restores, reset remains reachable.
10. **Complete game gate:** Play recorded saved decks through a complete native
    human-versus-AI game with defaults and customized layout/organization enabled.
    Include payment, stack choices, combat and Commander-specific interactions
    using dedicated scenarios where the full game's draw does not exercise them.
    Repeat four-viewer organization/control/reconnect scenario for CT-24. Record
    gaps explicitly; successful fixtures/concession alone are insufficient.

### Rollout and evidence policy

1. Land contracts/adapters with flags off; legacy arrangement stays selectable.
2. Enable private layout preview after CT-06; presets do not require networking.
3. Keep local grouping prototypes in fixtures until host authority, identity,
   multi-viewer projection, member access and reconnect pass CT-23. Then enable
   shared flat-group MVP for compatible sessions only.
4. Enable visual stacks/rules and later nesting/four-player scope separately after
   their native, privacy, reconnect and accessibility gates. Never silently turn on
   an unsupported rule or discard a saved preset.
5. Rollback switches rendering to legacy arrangement and stops new organization
   submissions; host can retain sidecar state for recovery. Do not alter native
   rules, replay game commands or overwrite private presets during rollback.

Implementation changes use GitHub Actions exclusively for suites. After an
authorized commit/push, inspect/record workflows for that exact SHA, considering
Python/Core, protocol, Java/XMage, licensed Unity, packaging and playable acceptance
as applicable. Start requested workflows and report links; per repository workflow,
do not poll long CI unless asked. Missing/skipped/cancelled/incomplete checks remain
open. Every Unity implementation change also requires the local Windows player
rebuild. This planning-only change requires neither a Unity rebuild nor a claim
that any suite has run. No commit, version bump, tag or release is implied by this
document; apply repository versioning when a documentation commit is requested.
