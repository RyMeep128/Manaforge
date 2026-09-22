# Manaforge — Long-Term Product Epic

## Product Vision

Manaforge should become a **local-first, open-source Magic: The Gathering workstation** built primarily for personal use and private play with friends.

The core idea is simple:

**Build → Test → Learn → Print → Play**

A deck should exist once inside Manaforge and flow naturally through every part of the application.

The user should be able to:

1. Search essentially the entire Magic card catalog.
2. Build and organize decks with excellent UX.
3. Get deterministic, data-driven recommendations and deck insights.
4. Select exact card printings.
5. Test decks locally and eventually against AI.
6. Print those exact cards as proxies.
7. Play the same deck digitally with friends.
8. Look up card rulings and the Comprehensive Rules without leaving Manaforge.

Manaforge is not intended to become a commercial live-service platform.

It should remain primarily:

* local-first
* offline-capable wherever practical
* user-owned
* modifiable
* open source
* private-play focused
* data-driven rather than dependent on generative AI
* usable without accounts or subscriptions
* capable of functioning even if external services disappear

If other people find Manaforge useful, great. However, product decisions should prioritize making an excellent tool for actually playing Magic rather than maximizing adoption.

---

# Core Philosophy

Manaforge should avoid unnecessary dependency on centralized services.

The user should own:

* their decks
* their downloaded card data
* their images
* their categories and tags
* their preferences
* their play history if implemented
* their local recommendation data
* their local rules reference

External services may be used to obtain or update data, but Manaforge should cache/store useful information locally and continue working wherever reasonably possible.

A user's install does not need to contain every Magic card image.

Manaforge should support two broad usage patterns:

### Full Archive

A power user may choose to download every English printing and maintain a very large local card archive.

### Build-As-You-Go

A normal user should be able to install Manaforge with only the core metadata and download card images/assets as they encounter or use them.

Missing assets should be fetched and cached automatically.

The game/deck model must therefore reference stable card/printing identifiers rather than depending on absolute local image paths.

---

# Product Areas

## 1. Card Library

Manaforge should function as a local Magic card database similar in capability to the parts of Scryfall useful for deck building.

Goals:

* local searchable card metadata
* Scryfall-style query syntax
* Oracle-level card identity
* printing-level identity
* all available English printings where downloaded
* exact printing selection
* local image caching
* optional full-card archive
* set information
* collector numbers
* artists
* legality
* color identity
* mana values
* types/subtypes
* Oracle text
* keywords
* prices only if useful and available without compromising offline behavior

Architecture should maintain a strong distinction between:

**Oracle Card**
and
**Printing**

A deck entry should reference the underlying card identity while optionally selecting a specific printing.

---

# 2. Deck Builder

The deck editor should become one of Manaforge's strongest features.

The desired experience combines useful ideas from tools such as Archidekt, Moxfield, and BlueprintMTG while remaining distinctly Manaforge.

Goals include:

* extremely fast card addition/removal
* Scryfall query support
* drag-and-drop organization
* exact printing selection
* custom categories
* automatic deterministic categories
* radial tagging/category UX
* deck statistics
* mana curve
* color distribution
* type distribution
* card-role distribution
* commander awareness
* legality checking
* duplicate restrictions
* deck templates
* deck notes if useful
* easy category editing
* fast visual scanning

Automatic categorization should remain deterministic and explainable.

Examples:

* Ramp
* Removal
* Draw
* Board Wipes
* Protection
* Counterspells
* Lands
* Tutors
* Recursion

Manaforge may also identify repeated Oracle/tag patterns and suggest additional deck-specific themes when a meaningful threshold is reached.

Example:

If 10+ cards strongly match a graveyard-related pattern, Manaforge could suggest a `Graveyard` category.

The user should always retain control over final categorization.

---

# 3. Recommendation System

Manaforge should eventually provide EDHREC-style recommendations without requiring EDHREC itself during normal use.

This should be **data-driven, not AI-generated**.

Potential recommendation signals:

* commander usage
* card co-occurrence
* deck archetypes
* color identity
* themes
* synergy tags
* card popularity
* mana curve needs
* card-role gaps
* deck composition

The desired recommendation UI should feel similar to browsing recommendations in Archidekt:

* card grid/list
* immediate `Add to Deck`
* expandable details
* card preview
* Scryfall syntax/filtering
* categories/themes
* clear reasons when practical

Recommendations should eventually be available offline after the relevant dataset has been downloaded.

---

# 4. Print System

The existing printer functionality remains a first-class Manaforge feature.

A user should be able to move directly from:

**Deck Editor → Print**

without exporting or recreating anything.

Printing should preserve the exact printing selected in the deck.

Goals include:

* high-quality proxy output
* accurate sizing
* configurable margins
* print calibration
* sheet optimization
* no wasted sheets for small card counts
* clear warnings for invalid/empty jobs
* preview
* multiple printings
* good handling of double-faced cards
* predictable output

The printer should continue to remain modular rather than leaking print-specific concerns into the core deck/card model.

---

# 5. Rules & Rulings

Manaforge should eventually include a first-class **Rules** section.

This is separate from the game rules engine.

The Rules section should function as a local reference library.

## Card Rulings

Searching for a card should show:

* card
* Oracle text
* official rulings
* relevant keywords
* links to related Comprehensive Rules sections

## Comprehensive Rules

Manaforge should contain a locally searchable copy of the Magic Comprehensive Rules.

Desired capabilities:

* full-text search
* rule-number search
* section navigation
* keyword index
* cross-links between rules
* version/date of installed rules
* easy updating when Wizards releases a new version

Example:

Searching:

`replacement effect`

should find the appropriate section.

Searching:

`614`

should navigate directly to Rule 614.

## Context Integration

Eventually, right-clicking a card anywhere in Manaforge could offer:

* View Card Details
* View Rulings
* Relevant Rules

During a game, players should be able to inspect rulings without leaving the match.

Rules/rulings data should be versioned separately from decks and artwork.

---

# 6. Playtest / Goldfish Mode

Before networking, Manaforge should gain a local playtest mode.

This should allow a deck to be opened directly from the editor.

Initial functionality:

* shuffle
* draw opening hand
* mulligan
* library
* hand
* battlefield
* graveyard
* exile
* command zone
* life
* commander damage
* poison
* counters
* tokens
* tap/untap
* draw
* mill
* move cards between zones
* restart game
* generate repeated opening hands

A basic manual playtest mode can exist before full rules automation.

Eventually, this mode should use the same game engine as AI and multiplayer.

---

# 7. Rules-Enforced Game Engine

The long-term goal is **Arena-like automation**, not merely a digital tabletop.

Manaforge should eventually understand enough Magic rules to automate ordinary gameplay.

Desired behavior:

* legal actions are known
* invalid actions are prevented
* valid targets are highlighted
* casting costs are calculated
* mana can be paid automatically
* triggered abilities are handled
* replacement effects are handled
* the stack is authoritative
* priority is tracked
* phases and steps advance correctly
* attacking/blocking restrictions are enforced
* damage resolves correctly
* state-based actions occur automatically
* tokens are created automatically
* counters are managed
* cards move to the correct zones
* hidden information remains hidden

The user experience should resemble **Magic Arena's level of assistance**, without attempting to recreate Arena's visual production budget.

Manaforge should automate bookkeeping while keeping the game understandable.

---

# Important Architecture Rule

Do **not** put Magic rules logic inside the UI.

The long-term architecture should resemble:

```text
Manaforge UI
    ↓
Game Client / Presentation Layer
    ↓
Game API / Adapter
    ↓
Rules Engine
    ↓
Game State / Card Definitions
```

The game engine should be deterministic and authoritative.

The UI should ask questions such as:

```text
What actions can Player A legally perform?
```

The engine may return:

```text
Play Forest
Cast Llanowar Elves
Activate Sol Ring
Pass Priority
```

A user action such as:

```text
CAST_CARD(instance_id)
```

should produce engine events rather than direct UI state manipulation.

Example:

```text
SPELL_CAST
MANA_PAYMENT_REQUESTED
STACK_CHANGED
PRIORITY_CHANGED
```

This separation is essential for:

* AI
* multiplayer
* testing
* replay
* undo where appropriate
* deterministic game state
* future UI changes

---

# 8. Existing Rules Engine Investigation

Manaforge should **not immediately attempt to implement all Magic rules from scratch**.

Before building the automated game engine, investigate mature open-source engines including:

* Forge
* XMage

Determine whether Manaforge can:

* embed one
* run one as a local subprocess
* communicate through an adapter/API
* translate Manaforge deck/card IDs into engine IDs
* receive authoritative game events/state
* preserve Manaforge's own UI

The goal is to reuse mature rules/card implementations while keeping Manaforge's application experience independent.

License compatibility must be evaluated before incorporating code.

Studying architecture is always acceptable; directly importing code requires license review.

---

# 9. AI Opponent

Manaforge should eventually support local AI play.

The goal is **useful deck testing**, not world-class competitive AI.

The AI should be capable of:

* making legal plays
* evaluating board state
* casting reasonably appropriate spells
* selecting sensible targets
* attacking/blocking intelligently
* using interaction
* understanding basic deck strategy
* presenting enough resistance to expose weaknesses in a deck

Potential progression:

### Level 1

Random legal actions.

### Level 2

Heuristic decision making.

### Level 3

Game-state evaluation/search.

### Level 4

More advanced matchup/deck-aware strategies.

If an adopted rules engine already contains usable AI infrastructure, prefer adapting it rather than starting from zero.

The AI does not need to use an LLM.

---

# 10. Private Multiplayer

Manaforge's multiplayer goal is playing with friends.

It is **not** intended to become a public matchmaking service.

Desired model:

```text
Host Game
↓
Invite Friend
↓
Friend Connects
↓
Play
```

Peer-to-peer networking should be preferred where practical.

A lightweight rendezvous/signaling service may eventually be necessary for NAT traversal, but the actual product should avoid unnecessary central infrastructure.

Initial multiplayer goals:

* private games
* direct invites / codes
* 1v1
* synchronized game state
* hidden information security
* reconnect support
* deterministic engine
* action/event log

Later:

* 3–4 player Commander
* spectators if useful
* saved/recoverable matches
* optional LAN play

Do **not** prioritize:

* public matchmaking
* rankings
* ladders
* user profiles
* social feeds
* monetization
* economies
* tournaments
* moderation systems

unless the personal use case changes.

---

# 11. Arena-Like UX

Gameplay should feel automated and readable.

Manaforge does not need Arena's animation budget.

It should borrow the interaction principles:

* obvious legal actions
* highlighted targets
* drag/click cards naturally
* clear stack visualization
* configurable priority stops
* automatic passing when appropriate
* attack-all / select attackers
* intuitive blockers
* automatic counter/token updates
* clear triggered ability prompts
* clean card zoom
* responsive battlefield
* understandable combat
* minimal unnecessary prompts

The primary goal is:

**reduce bookkeeping without hiding what Magic is doing.**

---

# 12. Unified Deck Model

The most important architectural concept is that a deck should not be recreated for each feature.

It should flow through Manaforge as the same object:

```text
Oracle Card
    ↓
Printing
    ↓
Deck Entry
    ↓
Deck
    ├── Builder
    ├── Recommendations
    ├── Analysis
    ├── Print Job
    ├── Playtest
    ├── AI Match
    └── Multiplayer Match
```

When a user changes the deck, every relevant system should naturally see the same change.

Avoid duplicate representations wherever possible.

---

# 13. Storage Model

Manaforge should support large local archives without requiring them.

Approximate philosophy:

### Core Installation

Contains:

* application
* card metadata
* database
* rules/rulings
* indexes

Should remain relatively small.

### Dynamic Assets

Artwork should download as needed.

```text
printing_id → local asset cache
```

If an image exists locally, use it.

If not:

1. locate the remote asset
2. download it
3. cache it
4. use the cached version thereafter

### Full Archive

Users may optionally download:

* every English card
* every English printing
* high-quality images

A full archive may consume 100+ GB and that is acceptable.

Manaforge should not compromise functionality merely to make the full archive tiny.

---

# 14. Non-Goals

Avoid turning Manaforge into six unrelated applications.

The following are not priorities:

* social network
* deck popularity contest
* public profiles
* follower system
* comments
* likes
* public competitive ladder
* card marketplace
* commercial subscription service
* cloud-only storage
* unnecessary accounts

The project exists to help the user **play Magic**.

---

# User Story / North Star

The ideal Manaforge workflow is:

> I have an idea for a Commander deck.
>
> I open Manaforge and build it.
>
> Manaforge automatically organizes obvious card roles and helps me identify themes.
>
> I browse recommendations and add cards.
>
> I choose the exact printings I like.
>
> I examine my curve, card roles, and composition.
>
> I immediately goldfish the deck.
>
> I play several games against AI.
>
> I discover six cards I dislike and replace them.
>
> I print those cards as proxies directly from the same deck.
>
> Friday night, I play the physical deck with my friends.
>
> Two weeks later we cannot meet in person, so I open the exact same deck in Manaforge and click Host Game.
>
> My friends connect and we play the same decks online with rules automation.
>
> Someone questions an interaction, so we right-click the card and open its rulings and relevant Comprehensive Rules.
>
> Nothing needed to be exported or recreated.

That is the long-term product.

---

# Development Strategy

Do **not** attempt this entire epic at once.

Recommended order:

## Phase 1 — Finish Build

Complete and stabilize:

* deck editor
* categorization
* tagging
* deck analytics
* printing selection
* recommendations
* persistence
* cohesive UI

## Phase 2 — Rules Reference

Add:

* card rulings
* Comprehensive Rules
* local search/indexing
* card → rules navigation

This is relatively low-risk and immediately useful.

## Phase 3 — Local Playtest

Build the reusable game-state model:

* players
* card instances
* zones
* turn state
* basic battlefield UI

Initially allow manual actions.

This phase should intentionally establish architecture usable by the future rules engine.

## Phase 4 — Rules Engine Prototype

Investigate Forge/XMage.

Create the smallest possible integration proof:

```text
Load Deck
→ Start Game
→ Draw Hand
→ Determine Legal Actions
→ Play Land
→ Cast Simple Spell
→ Resolve
```

Do not build sophisticated UI until engine feasibility is proven.

## Phase 5 — Arena-Like Local Play

Integrate:

* targets
* stack
* phases
* combat
* automatic rules
* priority
* triggers
* visual feedback

## Phase 6 — AI

Allow:

```text
Deck A: Human
Deck B: AI
```

Focus first on useful testing rather than AI strength.

## Phase 7 — Private 1v1

Move the authoritative game state into a networking-compatible architecture.

Implement:

* hosting
* joining
* synchronization
* hidden state
* reconnect

## Phase 8 — Commander Multiplayer

Extend networking and battlefield UX to support:

* 3–4 players
* commander damage
* shared combat state
* multiplayer priority
* larger battlefield layouts

## Phase 9 — Polish

Only after the complete loop works:

**Build → Test → Print → Play**

invest heavily in animations, transitions, visual effects, sound, onboarding, accessibility, and additional quality-of-life improvements.

---

# Engineering Principles

Throughout implementation:

1. **Keep modules separate.**
   Avoid god objects.

2. **Prefer stable domain models.**
   UI widgets should not become data models.

3. **Keep Oracle identity separate from printing identity.**

4. **Treat game cards as instances.**
   A battlefield card is not merely a database card.

5. **Keep rules logic outside presentation code.**

6. **Use events/actions for gameplay.**

7. **Make game state serializable.**
   This will matter for networking, saves, tests, replay, and debugging.

8. **Keep deterministic systems deterministic.**

9. **Design for local-first behavior.**

10. **External data should be cacheable.**

11. **Avoid feature duplication between components.**

12. **Test domain logic independently from the UI.**

13. **Do not sacrifice architecture purely for rapid feature implementation.**

14. **Refactor when boundaries become unclear.**

15. **Do not prematurely implement infrastructure that the personal use case does not require.**

---

# Immediate Guidance for Codex

This document is the **long-term architectural direction**, not an instruction to immediately implement Play, AI, networking, or a Magic rules engine.

Current work should continue focusing on completing and stabilizing the deck-editor experience.

When making changes today, however, avoid architectural decisions that would make this future difficult.

In particular:

* preserve stable card IDs
* preserve printing IDs
* keep decks serializable
* avoid coupling deck state directly to UI components
* keep the printer independent
* keep recommendation systems independent
* create clean service/domain boundaries
* avoid global mutable state where practical
* ensure future game objects can reference existing cards without altering the core card records

The desired outcome is that the current Manaforge can naturally grow into this architecture rather than requiring another full rewrite.

## Final Product Statement

**Manaforge is a local-first, open-source Magic workstation where a player can discover cards, build and analyze decks, choose exact printings, learn the rules, test against AI, print physical proxies, and privately play those same decks with friends through an automated digital game client—all without surrendering ownership of their decks or depending on a centralized platform.**
