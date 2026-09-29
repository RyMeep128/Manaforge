# Epic: Manaforge Play — Private Digital Magic & Playgroups

Status: **Planned long-term scope.** Delivery order and prerequisites live in the [roadmap](roadmap.md); the [long-term product epic](long-term-product-epic.md) remains the broader product vision. This epic does not authorize immediate gameplay implementation. XMage integration and optional external synchronization remain subject to feasibility, licensing, and supported capabilities.

## Vision

**Manaforge Play** turns the same decks built, analyzed, and printed in Manaforge into rules-enforced digital Magic games for private playgroups.

The goal is not to build another public Magic platform.

The goal is:

> **The software our playgroup uses to play Magic.**

A Manaforge deck should be usable without recreation for physical proxies, local testing, AI games, remote games with friends, borrowed-deck games, preconstructed-deck nights, and long-term playgroup statistics.

The complete loop becomes:

**Discover → Build → Recommend → Analyze → Test → Print → Play → Track → Improve**

Manaforge should remain usable even if external services disappear. External systems enhance Manaforge; they must not become required for access to decks, play history, or previously supported gameplay.

---

# 1. Stable Game Protocol

Manaforge must own the boundary between the application and any external rules engine.

```text
Manaforge UI
        ↓
Presentation / Automation
        ↓
Manaforge Game Protocol
        ↓
Engine Adapter
        ↓
XMage
```

Manaforge UI code must never depend directly on XMage classes such as its internal card, ability, permanent, or game-state objects.

Define versioned Manaforge concepts including:

```text
GameSnapshot
PlayerView
GameObject
LegalAction
ChoiceRequest
GameEvent
MatchSeat
CombatAssignment
```

Commands should include concepts such as:

```text
CreateGame
JoinGame
SubmitDeck
Mulligan
PerformAction
ChooseTargets
ChooseOption
PassPriority
DeclareAttackers
DeclareBlockers
Concede
```

### Acceptance gate

Manaforge gameplay and UI can run against a fake/test engine without XMage installed.

---

# 2. XMage Adapter & Upgrade Resilience

XMage is the preferred initial authoritative rules engine.

Manaforge must **not fork XMage into the application** or make its application model depend upon a particular XMage release.

Each Manaforge release should use a known compatible engine version:

```text
Manaforge version
Game Protocol version
XMage version/commit
Adapter version
```

XMage upgrades are deliberate:

```text
New XMage
    ↓
Build adapter
    ↓
Run compatibility suite
    ↓
Fix adapter if necessary
    ↓
Verify rules scenarios
    ↓
Approve
    ↓
Ship
```

An upstream XMage update must never silently replace the known-good engine underneath an installed Manaforge version.

Maintain automated scenarios covering basic casting through difficult multiplayer interactions.

The adapter maps stable Manaforge/Scryfall Oracle and printing identities to XMage definitions. XMage-specific class names or identifiers must not become persistent Manaforge deck identity.

### Acceptance gate

Upgrade between two supported XMage revisions without changing the Manaforge-facing game protocol or gameplay UI.

---

# 3. Rules-Enforced Local Play

XMage owns authoritative Magic rules.

Manaforge owns the experience.

Support:

- legal actions and targets
- mana and costs
- phases and steps
- priority
- stack
- triggered abilities
- replacement effects
- combat
- state-based actions
- counters
- tokens
- copying
- transform
- attachments
- multiplayer rules
- Commander-specific state
- hidden information.

The UI must operate on current **game objects**, not card names.

```text
GameObject
├── object_id
├── underlying card identity
├── controller
├── owner
├── zone
├── current characteristics
├── components
├── counters
├── attachments
├── effects
└── copy provenance
```

This model must support copies, token copies, mutate/merged permanents, face-down objects, transforms, control changes, and continuous effects without special UI hacks.

**Battlefield rule: show what the object currently is.  
Inspect rule: explain how it became that way.**

---

# 4. Adaptive 2–5 Player Battlefield

Manaforge Play officially targets:

**2, 3, 4, and 5 players.**

The protocol should not fundamentally assume five is the absolute engine maximum; 2–5 is the supported Manaforge product range.

The UI adapts rather than merely shrinking.

### Two players

Large head-to-head battlefield.

### Three players

Player's board emphasized with two opponent boards.

### Four players

Primary Commander layout with the player's battlefield largest and three stable opponent positions.

### Five players

Player battlefield remains readable while four opponent boards use more aggressive compression and grouping.

The interface has four principal contexts:

**Overview** — observe the complete table.

**Compare** — interact between two relevant players.

**Focus** — make a detailed decision involving one battlefield.

**Inspect** — understand one game object.

Player positions should remain spatially stable whenever possible.

---

# 5. Context-Aware Combat

Combat should automatically emphasize relevant battlefields without hiding the rest of the game.

When one player is attacked:

```text
Attacker ↔ Defender
```

becomes the emphasized comparison.

When attacks are split among multiple players, show a combat overview grouped by defender.

Each defender receives a personalized blocking view containing the creatures attacking them while retaining access to the rest of the table for interaction.

Use the existing Manaforge radial interaction language for combat.

Hold/right-click a legal attacker:

```text
Attack Player A
Attack Player B
Attack Player C
Attack Player D
Activate Ability
Other...
```

Only engine-provided legal actions are presented.

Support batch selection and count-based actions for interchangeable objects.

---

# 6. Calm Presentation of Complex Magic

The rules engine tracks exact state.

The player should see abstraction until individual distinctions matter.

Example:

```text
Risen Reef ×5
```

rather than five unnecessarily independent full-size objects.

Equivalent game objects may be visually grouped while retaining their individual engine IDs.

When one becomes different:

```text
Risen Reef ×4
Risen Reef — tapped/attacking
```

The same philosophy applies to triggers.

Instead of displaying 25 repetitive prompts:

```text
Risen Reef
25 triggers

[Resolve All]
[Resolve One]
[Inspect]
```

Bulk resolution is only available when rules/choices allow it.

Trigger inspection should explain provenance where possible:

> 5 Elementals entered. Five Risen Reefs triggered for each.

**Design principle:**

> **The crazier the Magic game becomes, the calmer Manaforge should become.**

---

# 7. Card Interaction & Explanation

Hovering a card/object displays a large readable card preview.

Clicking opens Inspect.

Inspect should distinguish the printed card from its current game state and show, when relevant:

- current characteristics
- Oracle text
- counters
- controller/owner
- attachments
- copied object
- component cards
- granted/removed abilities
- continuous effects
- relevant rulings
- provenance/history.

Inspect should answer:

> **What is this right now, and why?**

---

# 8. Player Seats & Mixed Human/AI Games

Gameplay should not have separate human and AI game modes.

Model a seat independently from its controller:

```text
MatchSeat
├── player
├── deck
├── pilot
└── controller
    ├── LocalHuman
    ├── RemoteHuman
    └── EngineAI
```

XMage's existing AI should be exposed initially where practical.

This allows:

```text
1 human + AI opponents
2 humans + AI opponents
3 humans + 1 AI
4 humans
4 humans + 1 AI
5 humans
```

A three-person playgroup can therefore simply:

> **Add Computer**

to create a normal four-player pod.

Manaforge-specific AI improvements may come later and must use the same legal-action protocol rather than bypassing the rules engine.

---

# 9. Private Host-Authoritative Multiplayer

Manaforge multiplayer is for friends, not public matchmaking.

Use a host-authoritative model:

```text
Clients
   ↓ commands
Host Manaforge
   ↓
Authoritative rules engine
   ↓
Visibility-filtered state/events
   ↓
Clients
```

The host controls authoritative rules state.

Clients never receive hidden opponent information merely to hide it in the UI.

Support eventually:

- LAN
- internet private games
- reconnect
- spectators
- saved/recoverable games
- action/event logs
- replay infrastructure.

Networking transport should remain replaceable.

The engine should not care whether the transport is localhost, LAN, direct internet, VPN-style networking, WebRTC, or a future relay.

---

# 10. Deck Ownership, Piloting & Borrowing

A deck's **owner** and its **pilot in a match** are separate concepts.

```text
Deck
owner = Player A

MatchSeat
pilot = Player B
deck = Player A's deck
```

Playgroup members may optionally make decks:

```text
Private
Visible to playgroup
Borrowable by playgroup
```

Borrowing does not transfer ownership.

A borrowed digital deck is made available for the match and retains its owner's deck identity.

Statistics should therefore support questions such as:

```text
How does this deck perform overall?
How does its owner perform with it?
How do other pilots perform with it?
How does Ryan perform when borrowing it?
```

AI players may also pilot borrowed decks.

---

# 11. Shared Deck & Preconstructed Library

Manaforge should support decks that aren't personally owned.

Examples include:

- playgroup decks
- borrowed decks
- imported public decklists
- preconstructed decks
- draft decks.

Preconstructed decklists can be imported or cached into a browsable library.

A playgroup can therefore decide:

> **Precon night.**

and assign available preconstructed decklists to seats without recreating decks manually.

All deck sources ultimately resolve into the same canonical Manaforge deck/game representation.

---

# 12. Playgroups

Manaforge may define a local **Playgroup** domain independent of external services.

A playgroup may contain:

```text
Members
Decks
Games
Custom ranking rules
Bracket configuration
Match history
Statistics
Sharing permissions
```

Playgroup data should remain local/user-owned and portable.

Cloud or third-party synchronization is optional.

---

# 13. Custom Playgroup Brackets

Do not assume official Commander bracket terminology matches a playgroup's terminology.

Support configurable playgroup ranking systems.

For the initial target playgroup:

```text
Bracket 1 = strongest/top-ranked decks
Bracket 2 = next group
...
```

with ten decks per bracket.

Example:

```text
Ranks 1–10   → Bracket 1
Ranks 11–20  → Bracket 2
Ranks 21–30  → Bracket 3
```

Store the bracket/ranking associated with a deck **at the time of a game** so historical games are not silently reclassified when rankings change.

Do not treat raw win rate as objective deck power; expose the underlying statistics separately.

---

# 14. Local Match History & Statistics

Manaforge owns the canonical local game record.

```text
Match
├── ID
├── date/time
├── players
├── pilots
├── decks
├── deck owners
├── commanders
├── starting player
├── turns
├── result
├── duration
├── elimination order
└── event log
```

Because the rules engine already observes game state, digital games should require essentially no manual stat entry.

Statistics may include:

- games
- wins
- finishes
- player/deck combinations
- commander performance
- matchup history
- turns
- duration
- ranking history
- bracket history.

This data remains useful without an external service.

---

# 15. Optional Playgroup.gg Integration

Playgroup.gg should be treated as an **adapter/synchronization target**, never as Manaforge's canonical database.

```text
                   ┌─ Manaforge local history
Game completed ────┼─ Manaforge analytics
                   └─ Playgroup.gg adapter
```

Where supported by its API, Manaforge may synchronize game/deck/playgroup information and consume useful external statistics.

Failure or disappearance of Playgroup.gg must not prevent:

- playing
- opening decks
- viewing local history
- computing Manaforge statistics.

---

# 16. Spectators

Spectators use the same game-state/view architecture as players.

```text
Authoritative GameState
       ↓
Visibility Policy
       ↓
SpectatorView
```

Initial spectators should see only information appropriate for normal observation.

Future consensual modes may include omniscient/replay views.

Spectators must never weaken hidden-information security for players.

---

# 17. Performance & Responsiveness

Manaforge should remain usable on ordinary modern laptops.

Target:

```text
Minimum:
4-core CPU
8 GB RAM
modern integrated graphics

Recommended:
6-core CPU
16 GB RAM
modern integrated graphics
```

Gameplay does not require a discrete GPU.

Do not render one expensive full-resolution widget per underlying engine object.

Use:

- thumbnail-sized assets
- lazy loading
- object grouping
- bounded image caches
- asynchronous engine/network work
- event/diff updates rather than routine full-state retransmission.

Local UI interactions should react immediately where safe while authoritative actions are confirmed by the host.

---

# 18. Local-First Preservation

A known-good Manaforge installation should remain capable of playing the Magic content it already knows even if upstream services disappear.

A preserved installation may contain:

```text
Manaforge
Compatible XMage engine
Manaforge/XMage adapter
Card database
Rules/rulings
Decks
Playgroup data
Recommendation aggregates
Cached assets
```

No external service is guaranteed forever.

Therefore:

**External systems provide updates and enhancements.  
They do not own the user's ability to play.**

Manaforge cannot make Magic intellectual property independent of its rights holders, but the technical design should preserve a playgroup's locally available decks, data, software, and previously supported gameplay.

---

# 19. Non-Goals

Manaforge Play does **not** initially need:

- public matchmaking
- ranked global ladders
- public profiles
- social feeds
- card marketplace
- digital ownership economy
- currencies
- battle passes
- monetization
- global tournament infrastructure.

Playgroup ranking is local and explicitly defined by that playgroup.

---

# 20. Updated North-Star Story

> I build a Commander deck in Manaforge.
>
> Manaforge categorizes it and shows me where I'm short on draw.
>
> I use the local EDHREC-style recommendations to finish it.
>
> I choose my favorite printings and print the proxies.
>
> Friday, we play it physically.
>
> Manaforge records the game in our playgroup history.
>
> Later, only three of us can play online. We start a four-player game and put an XMage-controlled AI into the empty seat.
>
> My friend wants to try my deck, so he borrows it directly from our playgroup library.
>
> Next week we decide to play only precons. We select four preconstructed decklists and start.
>
> During a complicated game, one player creates 30 token copies and dozens of triggers. XMage tracks every individual object while Manaforge groups the board into something humans can understand.
>
> Someone questions an interaction. We click the object and Manaforge explains its current characteristics and links to the locally stored relevant rulings.
>
> When the game ends, Manaforge saves the match locally and optionally synchronizes it with Playgroup.gg.
>
> Years later, even if an external deck site, statistics service, or rules-engine update disappears, our decks, play history, cached data, and known-good Manaforge/engine combination remain ours.

## Epic exit gate

**Two to five seats can form at a Manaforge table using any mixture of local humans, remote humans, and supported AI; select their own, borrowed, shared, or preconstructed decks; complete a rules-enforced game through a readable adaptive interface; preserve hidden information; reconnect when necessary; record the match locally; and optionally synchronize external playgroup statistics—without making any external service essential to continued play.**
