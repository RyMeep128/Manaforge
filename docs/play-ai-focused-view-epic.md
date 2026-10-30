# EPIC: Manaforge Play — AI & Arena-Style Experience Rebuild

**Priority:** High  
**Target:** Two-player offline Magic with XMage AI  
**Branch:** `feature/play-ai-focused-view`  
**Type:** Replacement experience / incremental architectural enhancement  
**Status:** Planned — awaiting implementation

## 1. Epic Overview

### Vision

Manaforge Play should let a player select one of their existing decks, choose an opponent, and enjoy a complete, rules-enforced Magic game through an intuitive, visually appealing interface.

The first playable target is **one local human versus one XMage AI**, operating completely offline once the match begins.

The interface should take inspiration from Magic: The Gathering Arena's usability, battlefield organization, card inspection, decision presentation, and match flow, without copying proprietary assets or rebuilding its visual engine.

Manaforge remains responsible for gameplay presentation and player interactions. XMage remains responsible for rules, priority, legal actions, AI, and authoritative game state.

This epic supersedes the current local pass-and-play UX. It does not discard the existing XMage adapter or validated gameplay contracts.

### Success statement

A user should be able to:

1. Open Play.
2. Select Play Offline.
3. Choose a format.
4. Select their own saved deck.
5. Choose an AI opponent's deck or randomize a legal deck.
6. Enter a game with clear loading progress.
7. View a large, readable opening hand and complete mulligans.
8. Play Magic through an immersive, responsive battlefield.
9. Cast spells, attack, block, use abilities, resolve choices, and inspect cards.
10. Finish a genuine XMage-enforced match and return cleanly to the lobby.

The process must not require a second human, a network connection during gameplay, or external websites.

---

## 2. Non-Negotiable Product Decisions

### Player and lobby model

- The local user always occupies their own seat.
- Other seats offer **Use AI** or **Invite Friend**.
- Invite Friend is unavailable until multiplayer networking is implemented.
- Do not expose technical player-controller abstractions in the UI.
- Internally, maintain independent match-seat, controller, player, pilot, deck, and ownership concepts.
- Preserve the ability to support 2–5 players later without imposing that UI complexity now.
- Remove local human-to-human pass-and-play and the handoff screen from the active Play experience.

### Play navigation

The landing screen includes:

- **Play:** Opens the match-mode selection flow.
- **Play Offline:** Direct entry to offline AI match setup.
- **Host Match:** Visible, explicitly unavailable until networking.
- **Join Match:** Visible on the right, explicitly unavailable until networking.

Do not simulate unavailable networking behavior or fabricate successful connections.

### Battlefield

- Enter gameplay in a maximized application window.
- Hide normal Manaforge workspace navigation while playing.
- Use a dedicated, Arena-inspired battlefield.
- The initial layout is **Focused View**, with one opponent above the local player.
- Focused View is permanent, not a temporary two-player implementation.
- Future 3–5-player matches will introduce additional switchable battlefield views.
- Do not build the complete multiplayer adaptive layout now.
- Preserve the ability to inspect all relevant information without cluttering the main battlefield.

### Cards and artwork

- Battlefield cards display the original printing's **name bar, artwork, and surrounding border**, with the lower rules-text area cropped away.
- Generate this battlefield representation locally using a standardized crop of the existing full card.
- No sophisticated frame recognition, custom-frame reconstruction, or special handling of unusual printings is required.
- Weird crops for showcase or full-art printings are acceptable for this milestone.
- Hovering displays the full card, readable rules text, and current game characteristics.
- Current counters, damage, tapping, power/toughness, and other gameplay changes remain live overlays or inspection data, not baked into cached artwork.
- Generated assets are shared by printing and face, not duplicated per deck.

### Offline asset policy

- No online artwork requests during a match.
- No online card metadata searches during a match.
- Prepare available artwork before entering gameplay.
- If artwork is missing, show a pre-match warning.
- Allow **Continue Anyway** or **Return to Lobby**.
- Use placeholders during gameplay where required.
- Defer advanced artwork repair and download workflows.

### Engineering rules

- Preserve the existing canonical DeckDocument and exact-printing identities.
- Do not implement Magic rules or independent AI logic in the UI.
- Preserve versioned gameplay contracts, seat-specific visibility, and authoritative decisions.
- Keep all engine and expensive artwork operations off the UI thread.
- Do not perform unnecessary unrelated refactors.
- Avoid introducing new network dependencies.
- Do not run local tests or local engine acceptance; add tests and let GitHub Actions CI execute them.
- Keep the installed Play feature gated until full acceptance.

---

# 3. Implementation Stories

## Story 1 — Prove XMage AI through the existing adapter

**Priority:** P0  
**Dependencies:** None

### User story

As a Manaforge player, I want to play against a computer opponent so I can test my decks without requiring another person.

### Requirements

Investigate the pinned XMage engine's AI controller and match-creation interfaces.

The current Manaforge bridge creates all seats as human players. Extend the bridge/adapter to configure one local human and one engine-controlled AI.

Prove that the AI can operate without a second human session or artificial UI button presses.

Validate:

- AI seat creation and deck assignment.
- Successful game initialization.
- Human opening-hand decisions.
- AI opening-hand handling.
- AI priority and turn advancement.
- AI land plays and legal actions.
- AI participation in combat.
- Game termination and cleanup.

Initially validate Freeform, followed by the existing supported two-player Commander configuration.

Preserve the pinned engine version and runtime integrity checks. Do not silently upgrade XMage.

### Acceptance criteria

- [ ] A real XMage match starts with one human and one AI.
- [ ] The AI takes turns autonomously.
- [ ] The human can legally interact with the AI through public adapter commands.
- [ ] AI decisions do not need Manaforge UI automation.
- [ ] Hidden AI information remains protected.
- [ ] Match results and cleanup are handled correctly.
- [ ] A headless pinned-engine CI acceptance scenario demonstrates the integration.
- [ ] Unsupported AI capabilities are documented rather than simulated.

**Gate:** Do not declare the AI playable or make the rebuilt UI depend on it until this scenario passes CI.

---

## Story 2 — Refactor match seats and controllers for future multiplayer

**Priority:** P0  
**Dependencies:** Story 1

### User story

As a player, I want a simple "You versus Opponent" experience now, without limiting Manaforge's ability to support multiplayer later.

### Requirements

Establish a clean separation between:

- Match seat
- Player identity
- Deck identity and owner
- Pilot/controller
- Engine session
- Authorized player view

Support LocalHuman and EngineAI now. Reserve RemoteHuman for future work without implementing networking.

The current user's seat is always the local human in the offline interface.

The opponent seat is assigned an AI controller. Later, the same lobby model can substitute or add invited human controllers.

Remove active pass-and-play and seat-handoff UI paths.

Retain the existing adapter's multiplayer-capable seat identity and authoritative visibility mechanisms.

### Acceptance criteria

- [ ] Offline games contain exactly one local human and one AI.
- [ ] UI code does not assume every seat is human.
- [ ] UI code does not require changing which human seat owns the screen.
- [ ] The game model remains compatible with 2–5 seats.
- [ ] No artificial five-player protocol maximum is introduced.
- [ ] Existing 2–5-seat adapter regression scenarios remain intact.
- [ ] Saved decks are not modified by match setup.
- [ ] Gameplay actions cannot be submitted on behalf of an unauthorized seat.

---

## Story 3 — Reliable startup, diagnostics, and game lifecycle

**Priority:** P0  
**Dependencies:** Story 1

### User story

As a player, I want a game to start reliably and explain what is happening so I never sit on an unexplained loading screen until it times out.

### Requirements

Audit the existing runtime startup, Java bridge, XMage server, player connection, deck resolution, match creation, and snapshot readiness sequence.

Replace generic waiting states with distinct, observable stages.

Diagnose the existing timeout paths and eliminate avoidable blocking or deadlocks without weakening correctness.

Ensure worker queues do not allow background polling or artwork operations to starve required gameplay commands.

Maintain safe handling of uncertain command outcomes; do not blindly replay potentially successful commands.

Track stage duration and stable error codes in diagnostic logs.

Provide safe cleanup after failed startup.

### Acceptance criteria

- [ ] UI remains responsive during every startup stage.
- [ ] Startup reports the actual stage being executed.
- [ ] Each timeout identifies its failing operation in diagnostics.
- [ ] A failed startup does not leave an inaccessible half-active match.
- [ ] Return to Lobby is possible after confirmed cleanup.
- [ ] No orphaned owned XMage processes remain after successful cleanup.
- [ ] No false progress percentages are shown.
- [ ] Repeated start/fail/retry/close cycles pass CI acceptance.
- [ ] No regression to engine-version validation or existing session safety.

---

## Story 4 — Redesign the Play landing page

**Priority:** P1  
**Dependencies:** None

### User story

As a player, I want an attractive, simple Play screen where starting a game is immediately obvious.

### Requirements

Replace the existing Play setup page with a dedicated Play landing screen.

Present Play and Play Offline prominently, with Host Match and Join Match grouped on the right.

Use Manaforge's existing visual language with larger artwork, deliberate spacing, clear typography, and restrained controls.

Play opens match-mode selection; Play Offline directly selects the available AI mode. Both reach the same underlying match setup rather than maintaining duplicate logic.

Host Match and Join Match are visible but clearly disabled or marked Coming Soon.

Opening Play must not launch XMage.

### Acceptance criteria

- [ ] Navigation is visually clear and consistent with Manaforge.
- [ ] Play Offline opens the offline setup path.
- [ ] Host and Join have no fake network behavior.
- [ ] Opening and leaving Play does not initialize the engine.
- [ ] Layout works at common desktop sizes.
- [ ] Existing Home navigation remains functional.

---

## Story 5 — Format-first lobby and deck selection

**Priority:** P1  
**Dependencies:** Stories 2 and 4

### User story

As a player, I want to select the match format before choosing decks, then prepare my own seat and opponent from one simple lobby.

### Requirements

Create a shared match-lobby model and UI.

Flow:

1. Choose supported format.
2. Enter lobby.
3. Choose local player's deck.
4. Configure opponent as AI.
5. Choose AI deck.
6. Start match.

Only expose formats currently supported by the adapter and verified for the chosen match type. Initially prioritize Freeform and Commander.

Show each seat clearly as **You** and **Opponent**.

The local human seat is fixed. The opponent seat offers Use AI and disabled Invite Friend.

Deck selection must use existing Core deck documents and preserve exact printings.

For Commander, publicly display other players' deck names and commander names/artwork in the lobby, but not full deck contents.

Provide access to local decks and, where the existing online library integration allows it, browsing or borrowing a shared deck before the match. A borrowed deck must become a local, isolated match snapshot.

Do not introduce new online library infrastructure as part of this story.

### Acceptance criteria

- [ ] Format is chosen before either deck.
- [ ] Both seats display correct deck names and available artwork.
- [ ] Commander lobby metadata is shown correctly.
- [ ] Ineligible decks cannot be started silently.
- [ ] Borrowed decks do not modify their owners' documents.
- [ ] Returning from preparation errors preserves lobby selections.
- [ ] No remote shared-library access is required once the match starts.
- [ ] Future 3–5-seat lobby expansion does not require a completely different setup model.

---

## Story 6 — AI deck selection and Randomize

**Priority:** P1  
**Dependencies:** Stories 1 and 5

### User story

As a player, I want to select a particular deck for the AI or press Randomize to find a legal opponent automatically.

### Requirements

In the opponent panel, provide:

- Select Deck
- Randomize
- Chosen deck name
- Commander display, when applicable
- Validation/readiness state

Randomize selects from available saved decks verified to be eligible for the chosen format and supported by the pinned engine.

Randomization must never silently substitute a different deck after selection.

If no eligible decks exist, explain that clearly.

The selected AI deck must use the ordinary Core deck representation and match preparation pipeline.

### Acceptance criteria

- [ ] User can select a specific AI deck.
- [ ] Randomize selects an eligible legal deck.
- [ ] Unsupported decks are excluded or explicitly rejected by preflight validation.
- [ ] Commander-specific requirements are respected.
- [ ] No eligible decks produces a clear message, not an infinite retry.
- [ ] Repeated randomization can select different eligible decks.
- [ ] The chosen deck is shown before the match starts.
- [ ] AI receives the selected deck without modifying the original document.
- [ ] No online dependency is introduced.

---

Story 6 incremental implementation (0.5.10-alpha.1): the worker-facing adapter
now offers uncached pinned-engine deck validation before match creation. It uses
ordinary Core translation and the same XMage deck loader and format validators
as table joins. Explicit ineligibility remains distinct from translation,
transport, engine-load, and malformed-response failures. Private validator
messages are not returned. CI coverage adds source preservation and strict
response checks; the existing AI Freeform engine scenario now requires the same
deck to pass Freeform validation and fail Commander validation before gameplay.
These checks have not been run locally. Randomize selection, cancellation,
cleanup recovery, and UI integration are still pending; this is not completion
of Story 6 or an eligibility cache.

## Story 7 — Local battlefield artwork generation

**Priority:** P1  
**Dependencies:** Story 5

### User story

As a player, I want cards on the battlefield to resemble compact Arena cards, displaying their names, artwork, and borders without occupying space for unreadable rules text.

### Requirements

Extend the existing artwork system with a generated battlefield image variant.

Use the locally cached full printing image as the source.

Generate a consistent upper-card crop containing:

- Card name bar
- Original artwork
- Surrounding card border

Crop away the rules text and lower portion.

Use a straightforward image crop. Do not attempt comprehensive special-frame detection.

Cache by printing ID, card face, rendering version, and needed resolution.

Preserve the full original printing for detailed inspection.

Support transformed faces using the existing card-face identity handling.

No duplicated deck documents or per-deck full-image copies.

Do not bake live gameplay values into generated thumbnails.

### Acceptance criteria

- [ ] Standard cards display their names, art, and borders.
- [ ] Battlefield thumbnails have no normal lower rules-text area.
- [ ] Repeated printings share the generated cache.
- [ ] Generated assets are reused across matches.
- [ ] Unusual printings are allowed to crop imperfectly.
- [ ] Double-faced card rendering follows the current displayed face.
- [ ] Missing images produce a placeholder rather than an exception.
- [ ] Full original card images remain accessible.
- [ ] Generation runs asynchronously and does not freeze the UI.

---

## Story 8 — Pre-match asset preparation and strict offline gameplay

**Priority:** P0  
**Dependencies:** Stories 5 and 7

### User story

As a player, I want my match to use locally available artwork and data without downloading anything while I play.

### Requirements

Introduce a pre-match preparation stage.

Resolve the selected decks and locally available artwork. Generate or reuse needed battlefield thumbnails before entering the game.

Produce a match-scoped asset manifest or equivalent frozen set of references.

Explicitly disable remote artwork fallbacks in active Play image loading, including face-image loading and inspection.

If artwork is missing, display a warning identifying the missing cards and offer:

- Continue Anyway
- Return to Lobby

Do not build an advanced download/repair flow in this epic.

Tokens, copied objects, generated objects, and unusual engine-created representations must work with locally available images or graceful placeholders.

Do not block engine actions because artwork is unavailable.

### Acceptance criteria

- [ ] No online image requests occur during gameplay.
- [ ] No online metadata requests occur during gameplay.
- [ ] A normal fully cached deck enters gameplay without artwork warnings.
- [ ] Missing artwork generates a clear pre-match warning.
- [ ] Continue Anyway launches the match with placeholders.
- [ ] Return to Lobby preserves selections.
- [ ] Hover and inspection never trigger remote downloads.
- [ ] Locally generated assets are reusable.
- [ ] CI includes a network-denied gameplay test.

---

## Story 9 — New immersive Focused View battlefield

**Priority:** P1  
**Dependencies:** Stories 2 and 7

### User story

As a player, I want the game screen to feel like playing Magic rather than using a database management interface.

### Requirements

Replace the existing scroll-heavy battlefield layout with a dedicated Focused View.

Automatically maximize the application when entering a match. Retain normal OS window controls and clean restoration when leaving gameplay.

Position:

- Opponent information and hand at the top.
- Opponent battlefield in the upper portion.
- Shared combat/stack area where relevant.
- Local player's battlefield in the lower portion.
- Local hand along the bottom.
- Life totals and key game indicators near the corresponding player.
- Primary turn/priority controls near the right edge.

Avoid persistent sidebars consuming major battlefield space. Inspection and decisions should appear contextually.

The first layout supports exactly two visible players. Its sizing should remain usable on different desktop resolutions without implementing multiplayer seat arrangements.

Internally introduce a view-mode boundary so future matches can switch between Focused View, Overview/Table View, and specialized contexts.

The local battlefield remains persistent when a different opponent is focused in future multiplayer.

### Acceptance criteria

- [ ] Gameplay enters a maximized, immersive layout.
- [ ] Opponent is visually above the local player.
- [ ] Local hand is immediately visible.
- [ ] Normal gameplay does not require navigating scrollable zone tabs.
- [ ] Life totals, phases, priority, and important controls remain understandable.
- [ ] Focused View works in a two-player game.
- [ ] Resizing does not make controls inaccessible.
- [ ] No 3–5-player adaptive board is implemented.
- [ ] Future view switching remains architecturally possible.

---

## Story 10 — Card hover, inspection, and interactions

**Priority:** P1  
**Dependencies:** Story 9

### User story

As a player, I want to understand and interact with cards directly without permanently displaying their full rules text on the battlefield.

### Requirements

On the battlefield, use simplified card images with compact live indicators where appropriate.

Hovering a card opens a readable large preview showing the full printing and authoritative current game information.

Include current:

- Name and characteristics
- Mana cost and type when available
- Rules text/current abilities where supported
- Power/toughness, loyalty, or defense
- Counters and damage
- Relevant modifications, copy state, or transformed face

Do not represent obsolete printed characteristics as though they are current engine state.

Left-click interacts with an engine-offered legal action. When multiple actions exist, show a compact choice menu.

Right-click provides persistent detailed inspection without activating the card.

Keep legal-action highlighting clear but unobtrusive.

Support tapped orientation, attacking/blocking indicators, and target selection.

### Acceptance criteria

- [ ] Battlefield cards remain compact and art-focused.
- [ ] Hover previews display large readable cards.
- [ ] Current engine values are distinguishable from printed values.
- [ ] Right-click inspection never submits an action.
- [ ] Single-action interactions are straightforward.
- [ ] Multiple legal actions remain selectable.
- [ ] Hidden cards cannot leak information through artwork or inspection.
- [ ] Existing object identity and stale-command protections remain intact.

---

## Story 11 — Arena-style mulligans and decision presentation

**Priority:** P1  
**Dependencies:** Stories 1, 9, and 10

### User story

As a player, I want clear, prominent choices when opening a game or resolving Magic effects.

### Requirements

Create a dedicated opening-hand overlay:

- Dim the battlefield.
- Present the opening hand as large, fanned, readable cards.
- Provide prominent Keep and Mulligan controls.
- Display the correct number of cards and required bottom-of-library selections.
- Show appropriate opponent readiness or waiting status.

The AI handles its own mulligans.

For in-game decisions, show contextual panels or overlays rather than forcing the user into a permanent sidebar.

Support engine-provided legal choice families including targets, options, additional costs, mana payments, ordering, selections, and amount allocation.

Choice prompts should show meaningful cards/artwork wherever appropriate.

Keep cancellation and selection-completion behavior tied to actual engine permissions.

### Acceptance criteria

- [ ] Opening hands are large and readable.
- [ ] Keep and Mulligan are unambiguous.
- [ ] Required bottom-card selections work.
- [ ] AI mulligans progress without human control.
- [ ] Choice dialogs show the relevant card or options.
- [ ] Targets and selections clearly indicate their current state.
- [ ] No decisions are automatically answered on the human's behalf.
- [ ] All submitted decisions use current authoritative decision tokens.
- [ ] Unsupported decisions show actionable failure/recovery information.

---

## Story 12 — Priority, combat, stack, and match completion

**Priority:** P1  
**Dependencies:** Stories 1 and 9–11

### User story

As a player, I want the interface to make normal Magic actions natural, including casting, paying costs, attacking, blocking, and passing priority.

### Requirements

Make the normal turn flow visible and intuitive.

Present a contextual Next / Pass Priority control with accurate descriptions of the next available action.

Show the active player, current phase, and current priority holder.

Use readable stack presentation when spells and abilities are waiting to resolve.

For combat, make attackers, blockers, defenders, and relevant assignments obvious.

Preserve engine authority over combat legality, damage, mana, and triggered abilities.

Maintain a readable result display and clean return-to-lobby action.

Avoid excessive animations or effects at this stage. Prioritize responsiveness and correctness.

### Acceptance criteria

- [ ] Player can play lands and cast supported spells.
- [ ] Mana payments and choices work through XMage.
- [ ] Priority passes correctly between the human and AI.
- [ ] Attacking and blocking interactions are clear.
- [ ] Stack objects are inspectable.
- [ ] Triggers and choices remain accessible.
- [ ] Game results reflect the engine's authoritative outcome.
- [ ] A completed game can be closed without leaving stale engine processes.
- [ ] Ordinary card interactions do not require multiple unnecessary confirmation screens.

---

## Story 13 — Loading screens, recovery, and diagnostics integration

**Priority:** P1  
**Dependencies:** Stories 3–12

### User story

As a player, I want meaningful loading feedback and a simple way to recover from a failed match without losing my decks or leaving Manaforge in a broken state.

### Requirements

Build two distinct loading experiences:

**Lobby preparation**

Show actual deck/library preparation work, loading of metadata, and readiness states.

**Match initialization**

Use the available screen to display meaningful runtime stages.

Do not show simulated progress. Real stages and elapsed time are preferable.

When failures occur, retain diagnostic details internally and present simple options to the player.

Integrate with Manaforge's existing feedback/diagnostics workflow. Include permitted session metadata, app version, engine version, error codes, and sanitized logs when available.

Never automatically include opponents' private decks, unrevealed cards, credentials, or other sensitive contents.

### Acceptance criteria

- [ ] Lobby and game loading are visually distinct.
- [ ] Each loading state corresponds to real work.
- [ ] Error messages are understandable.
- [ ] Diagnostics preserve enough information to investigate failures.
- [ ] Recovery does not blindly replay uncertain commands.
- [ ] Exiting a failed session cleans up owned resources.
- [ ] User can return to the lobby and retry safely.
- [ ] No saved deck or printing selection is modified.
- [ ] Feedback respects existing privacy/consent behavior.

---

## Story 14 — Real-game acceptance, visual review, and documentation

**Priority:** P0 release gate  
**Dependencies:** Stories 1–13

### User story

As a developer and player, I want evidence that Manaforge Play is genuinely usable rather than merely passing isolated adapter tests.

### Requirements

Extend the existing Play acceptance infrastructure rather than replace it.

Add an end-to-end scenario covering:

1. Open Play.
2. Select Play Offline.
3. Select supported format.
4. Choose user and AI decks.
5. Validate and prepare assets.
6. Start the pinned XMage runtime.
7. Reach opening hands.
8. Complete the human mulligan decision.
9. Allow AI to act.
10. Play a supported land and spell.
11. Advance priority and turns.
12. Complete combat.
13. Reach an authoritative match result.
14. Return to the lobby and clean up.

At least one real-engine end-to-end scenario must reach a normal game conclusion rather than relying exclusively on concession.

Continue the existing headless adapter scenarios and 2–5-seat compatibility checks. Retire or update obsolete pass-and-play UI tests without removing meaningful hidden-information or lifecycle regressions.

Produce CI screenshots of the lobby, loading screen, opening hand, battlefield, hover preview, choice overlay, combat, and final result.

Perform visual review using real printing images, not only synthetic fixture artwork.

The user's manual nightly UX testing remains an explicit acceptance requirement.

### Acceptance criteria

- [ ] Existing relevant unit and integration tests pass in CI.
- [ ] Pinned-engine human-versus-AI acceptance passes in CI.
- [ ] At least one complete rules-enforced game is demonstrated.
- [ ] UI screenshots are saved as reviewable CI artifacts.
- [ ] No gameplay network-artwork requests occur.
- [ ] Startup/recovery/cleanup scenarios pass.
- [ ] Existing non-Play workspaces are not regressed.
- [ ] Real printing images are visually reviewed.
- [ ] Human testing confirms that the basic game is comfortable and understandable.
- [ ] Documentation reflects the new offline Play workflow and its limitations.

**Do not mark this epic complete based solely on green CI if the actual UI remains difficult to use.**

---

# 4. Delivery Milestones

| Milestone | Stories | Required result |
|---|---|---|
| A — Engine & reliability | 1–3 | Real AI match can start and progress, with reliable lifecycle management |
| B — Match preparation | 4–8 | New landing page, usable lobby, deck randomization, fully local assets |
| C — Gameplay experience | 9–12 | Maximized Focused View, clear cards, mulligans, and normal interactions |
| D — Production-quality preview | 13–14 | Diagnostics, CI evidence, visual review, and a demonstrated playable match |

Stories may be split into smaller commits. Do not sacrifice independently verifiable behavior for a large one-shot implementation.

---

# 5. Explicit Non-Goals

This epic does not include:

- Networked hosting, inviting, or joining.
- Public matchmaking.
- 3–5-player battlefield layouts.
- Fully adaptive multiplayer rendering.
- Building new AI decision algorithms.
- Replacing or forking XMage.
- Full recreation of every Magic card frame.
- Comprehensive card-layout crop detection.
- Dynamic rewriting of full printed card frames.
- Elaborate artwork repair or download interfaces.
- Particle effects, elaborate animations, or sound systems.
- Spectators, reconnection, or replay systems.
- Match history, rankings, or tournament support.
- General rewrites of the Deck Editor, Proxy Printer, or Card Database.

Future-facing contracts and boundaries are encouraged. Implementing future features is not.

---

# 6. Architectural Constraints

Reuse and extend existing Manaforge facilities wherever practical:

- `mtg_play/adapter.py` — authoritative game integration.
- `mtg_play/contracts.py` — versioned gameplay representations.
- `mtg_play/java/ManaforgeBridge.java` — XMage interaction.
- `mtg_play/presentation.py` — asynchronous session control.
- `mtg_play/workspace.py` — Play navigation and lifecycle.
- `mtg_play/table.py` — replace/refactor current battlefield presentation.
- `mtg_play/decisions.py` — engine-authorized decision presentation.
- `mtg_play/artwork.py` — extend for local derived battlefield artwork.
- Existing Core deck, artwork, library, and diagnostics services.

Avoid moving gameplay rules into Qt.

Separate:

**Authoritative state → presentation/view model → battlefield renderer → player interaction**

The renderer should receive permitted, normalized state and must not need to know how XMage internally represents that state.

The final architecture must support adding new view modes and controller types without rewriting the authoritative game model.

---

# 7. Codex Implementation Requirements

1. Create `feature/play-ai-focused-view` from the latest intended integration base. Do not make unrelated changes to main.
2. Inspect the actual repository, current Play docs, roadmap, and relevant tests before implementation. Do not assume prior implementation status from story descriptions.
3. Preserve the pinned XMage runtime and existing compatibility manifest unless a separate, justified change is approved.
4. Implement stories in dependency order, with small, reviewable commits.
5. Add and update appropriate unit, integration, Qt interaction, and real-engine acceptance tests.
6. **Do not run local tests, local builds, or local XMage acceptance. Use GitHub Actions CI as the execution environment.**
7. Do not claim a pass without identifying actual CI evidence.
8. Address CI failures introduced by the branch; report unrelated pre-existing failures separately.
9. Preserve offline behavior, existing saved data, printings, and other Manaforge modules.
10. Use asynchronous workers and bounded caches; don't block the UI with engine or image preparation.
11. Update `docs/play-local-game.md`, `docs/roadmap.md`, and the relevant long-term Play epic to distinguish implemented behavior from future plans. Keep the existing long-term 2–5-player roadmap intact.
12. Do not enable installed/released Play by default until its acceptance gates are met.
13. Do not create a release, tag, or merge to main automatically.
14. At each story handoff, provide changed files, commit SHA, CI results, verification gaps, and remaining risks.
15. Do not mark the overall epic complete until all acceptance gates and manual UX review are satisfied.

---

# 8. Final Epic Definition of Done

Manaforge Play is considered successful when:

- One human can play against XMage AI without another person.
- The AI can use a user-selected or randomized legal deck.
- A player can launch a match from a clear, format-first lobby.
- Startup is reliable, understandable, and recoverable.
- Games run offline with no mid-match artwork or metadata downloads.
- Battlefield cards display name, art, and border.
- Hovering provides readable full-card and live-state inspection.
- Mulligans and choices are clear and visually prominent.
- The two-player Focused View is attractive, responsive, and enjoyable.
- Standard gameplay interactions are accessible and rules-enforced.
- A genuine game can progress to an authoritative result.
- Existing decks and other application modules remain intact.
- CI and manual UX verification both support the playable claim.
- The design is positioned for future invited friends, AI-filled seats, and switchable views in 3–5-player games.

**Guiding principle:**

*Manaforge owns the experience. XMage owns the rules. The player should enjoy the game rather than fight the interface.*

CI investigation (0.5.11-alpha.1): completed run 40981801955 at e6f9e1a
confirmed the same obsolete source-document identity assertion on both Python
versions (already corrected locally in d455c14). The Python 3.12 headless and UI
AI blockers scenarios also stopped at GAME_CHOOSE_ABILITY with one offered
option. Both runtimes shut down cleanly. The blockers-only fixture pilot now
accepts a sole engine-offered ability for its authorized human viewer, using the
current decision and option tokens. Multiple options, foreign viewers and other
fixture policies remain rejected. Both acceptance drivers use this shared pilot;
no product auto-answering was added. CI tests cover these bounds. No local tests,
builds or engine acceptance were run, and these fixes remain unpushed/unverified
by a subsequent CI run.


Story 6 incremental implementation (0.5.12-alpha.1): the opponent panel now has
Randomize. An explicit click starts a separate worker-owned offline runtime,
clones the ordinary Core documents, and asks the pinned engine to validate every
candidate for the chosen format. Translation failures and explicit validator
rejections exclude a candidate; uncertain validation aborts the attempt. No
eligibility cache is retained. When several decks pass, the next choice excludes
the current opponent. The chosen deck is applied only after confirmed cleanup,
and remains visible in the existing selector, commander/artwork and readiness
presentation before Start Game. Match startup still prepares that exact selected
document through the ordinary pipeline.

Cancel waits for an in-flight engine call and then cleans up without replacing
the selection. Empty pools and failures preserve the selection with a clear
message. Unconfirmed cleanup retains runtime ownership, blocks startup and
navigation, and exposes an explicit cleanup retry; workspace closure also waits
for cleanup. Setup edits and catalog refresh are blocked during preparation.
Opening Play does not start a runtime. No network or source-document writes are
introduced. CI regressions cover worker isolation, candidate exclusion,
rerandomization, cancellation, cleanup recovery, and lobby gating. Tests/builds
and engine acceptance have not been run locally. Story 6 remains pending CI and
manual UX verification; this entry does not declare its acceptance criteria met.


Story 7 incremental implementation (0.5.13-alpha.1): active Play now uses its
own asynchronous local-only printing reader instead of the editor reader's
remote fallbacks. Battlefield objects request a straightforward upper 58 percent
crop preserving the source name bar, artwork and border; hand/other zones and
detailed inspection retain the full image. Compact battlefield cards keep live
stats and interactions outside the cached bitmap. No special-frame detection
or live gameplay values are baked into images.

Derived PNGs are atomically cached under the shared Core data directory by exact
printing, face, flip orientation, rendering version, resolution and source digest.
Repeated printings and later matches reuse these files; replacing a cached source
produces a new derivative. Original files remain unchanged. Alternate faces use
their local face variant; classic flip faces rotate their shared source first.
Missing/corrupt local images return placeholders. Play's image reader calls no
ensure/download APIs. CI regressions cover crop content, cache reuse and source
invalidation, full inspection, missing/corrupt sources, exact alternate/flip
faces, and worker-thread/local-only access. No local tests/builds or visual
acceptance have been run. Story 8 still needs pre-match asset preparation and
missing-artwork Continue/Return handling, including settling lobby image work
before gameplay; strict offline gameplay is not yet declared accepted.


Story 8 incremental implementation (0.5.14-alpha.1): Start Game now prepares
local artwork on a separate queue using isolated Core deck copies. It resolves
selected printing/front/alternate-face references and generates/reuses battlefield
crops. A match manifest freezes local source paths, SHA-256 digests and layouts;
active artwork/inspection use only that manifest. Changed or unlisted images,
including unknown generated objects, produce placeholders. No network or live
catalog fallback is exposed by the frozen image service. Original deck documents
and full printing images remain untouched.

Preflight waits asynchronously for any lobby image worker already in flight
before launching the engine. Missing or undecodable artwork is listed in a
plain-text review page with Continue Anyway and Return to Lobby. Fully cached
decks proceed without a warning. Returning/cancelling preserves both selections,
waits for worker completion, and does not start a runtime. Setup/navigation and
closure are gated while preparation is active. The CI UI pilot now explicitly
uses Continue Anyway for its intentionally uncached synthetic fixture printings.
CI regressions cover frozen references/source changes, crop generation, front and
alternate-face inspection with network/live catalog denied, warnings, normal
cached startup, cancellation, source preservation and explicit continuation.
No local tests/builds or engine acceptance were run. Story 8 and strict offline
UX remain pending CI and manual verification rather than declared complete.


Story 9 incremental implementation (0.5.15-alpha.1): the first Focused View
removes the whole-board vertical scroll area and permanent inspection sidebar.
Opponent information/battlefield sit above the local player/battlefield and
bottom hand. The stack appears directly between battlefields only when occupied,
with a contextual combat summary. Public secondary zones remain accessible in a
separate nonmodal window, which opens for a newly offered object choice in those
zones. Inspection and object action choices use a separate contextual window;
closing inspection does not reopen it on every snapshot. Clear/conceal hides both
windows and erases their contents. Decision controls remain at the right edge.

A Focused View mode entry point currently accepts only the supported focused
mode. Local and opponent battlefield widgets retain separate identities; no
multiplayer adaptive layout or opponent switching is introduced. Card lanes fit
the available height/width, including when the shared stack is visible, while
retaining horizontal access to crowded zones. Match startup saves the containing
window's geometry/state and maximizes it, reduces workspace chrome, and restores
the original state on leaving gameplay or failed startup. Native OS window
controls remain available.

CI regressions cover board ordering and viewport bounds at two desktop sizes,
stack visibility, right-edge decisions, contextual inspection/zone privacy and
non-submission, dismissal persistence, mode boundaries, and restoration of normal
and already-maximized windows. Existing object/decision token handling remains
in place. Formatting and diff checks only were performed locally: no tests,
builds, engine acceptance, or manual visual verification. Story 9 remains pending
CI/UX acceptance; hover previews and further contextual interaction polish belong
to the following story.


Screenshot feedback fixes (0.5.16-alpha.1): format Continue/Back and lobby match
actions now follow their content instead of being pushed to the bottom by
stretch spacers. Match readiness sits beside Start, identifies the blocking seat
and reason, and is also its tooltip. Primary disabled buttons now have an explicit
disabled style so Start no longer looks active while gated. Unknown active deck
sections remain blocked and are identified by name.

Read-only inspection of the user's local precon files identified the actual
Adaptive Enchantment blocker as its `display_commander` section. Core precon
imports intentionally keep oversized display cards separate from playable cards.
Play translation/readiness and artwork preparation now omit that display-only
section without altering the source document; genuinely unsupported gameplay
sections remain rejected. CI regressions cover exclusion and exact source
preservation.

Randomize and match startup now display a dedicated loading page with stage
messages, indeterminate progress, elapsed time and explicit cancellation. Match
startup switches to the battlefield only after an authorized snapshot arrives;
cleanup remains owned and retryable. Artwork preparation also has a visible
progress bar before any missing-artwork review. Overall status text appears near
the top instead of below the lobby's bottom edge. CI checks cover loading state,
compact action placement, explanatory gating and section handling. Only static
inspection, formatting and diff checks were performed locally; no tests, builds,
push or CI monitoring.


Startup investigation (0.5.17-alpha.1): the user's 20261029-205003-e8e38cd0
runtime connected successfully and exited cleanly. The application recorded a
deck-resolution failure at 20:50:38 but discarded its underlying exception code;
this evidence does not identify or fix the original resolution cause. Startup
now records a fixed, allowlisted cause code before cleanup and preserves it with
the lifecycle stage in the user-facing error. Database, transport/protocol and
internal type/interface errors are distinguishable without exporting raw
exception messages or private deck payloads. A subsequent attempt is needed to
identify the actual cause; no engine was started locally for this investigation.

The display-card behavior is section-wide, not name-specific: all
`display_commander` entries are omitted from translation and asset requirements.
Expanded CI coverage includes multiple differently named/future unresolved display
cards in Freeform and Commander translation, immutable source documents, asset
exclusion, and safe cause propagation after confirmed cleanup. No local tests or
builds were run. The original startup failure remains unresolved pending its
new diagnostic cause code.


Startup/cancel bug fixes (0.5.18-alpha.1): static inspection identified the actual
translation defect: prepare_deck used commander_ids after the local-readiness
refactor had moved its definition into _deck_queries. Successful mainboard
resolution therefore raised NameError while routing cards. The translator now
builds that set from its own document before routing mainboard/commander entries;
this is an application defect, not evidence of an illegal user deck. Safe cause
classification also recognizes NameError for future diagnostics.

Randomize and match startup now bind a shared cancellation event to the owned
adapter. Server-startup and bridge-connect/handshake waits check it in short
intervals and enter the existing owned-process cleanup path instead of waiting
for startup to complete. Phase boundaries also check cancellation before new
startup work. Match stop signals this token while still opening, without
interrupting/replaying established gameplay commands. Cancellation remains
cooperative: synchronous workspace preparation/compilation must finish their
current step before cleanup; the UI returns only after cleanup is confirmed.
CI regressions cover mainboard/legacy commander routing, cancelled server/bridge
waits, and cancellation propagation/cleanup for both startup controllers. No
local tests, builds or engine acceptance were run; fixes remain pending CI/user
verification and are not pushed.


CI repair verification (0.5.19-alpha.1): run 40986305301 at a6107df failed on
both Python versions because Play and Editor tests shared the test_readiness.py
module basename. Play's module is renamed test_play_readiness.py. The separate
commander_ids NameError seen by lint and engine scenarios is fixed in 2f9bee1.
An unused test import is removed. Engine acceptance scope now requires successful
application tests, preventing long engine runs after basic collection failures.

Local focused verification is explicitly authorized by the user's latest request.
On Python 3.13, all Play tests plus Editor readiness pass (265 tests); the exact
CI application-suite roots collect successfully (1823 tests). The broader
collection initially stopped because this local interpreter lacked QtPdf; using
the repository-pinned PyQt6 6.11.0 resolved that environment mismatch. Repository
Ruff lint, scoped formatting and diff checks pass. No local XMage acceptance or
application build was run. The accumulated commits are pushed at the user's
explicit request; further epic work remains local unless separately authorized.
