Owner-supplied story, October 31, 2026. The reviewed baseline below is historical;
see [current implementation and pin evidence](play-payment-coordinator.md).

# Story: Java Gateway — Safe Automatic Mana Payment

**Type:** Feature Story\
**Priority:** High — Play MVP\
**Target:** Manaforge Play, Java Gateway\
**Roadmap placement:** Phase 2, P2.3 (Decisions), with integration acceptance in Phase 4, P4.3\
**Baseline reviewed:** `feature/play-bound-command-dispatch`, `0.5.102-alpha.1`\
**Implementation:** Codex\
**Status:** Ready for implementation planning; live execution depends on Java/XMage integration.

---

## 1. User story

As a Manaforge Play user, I want the Java gateway to automatically pay mana costs when it can safely determine how to do so, so that I can cast spells and activate abilities without manually selecting individual mana sources every time.

The experience should feel similar to MTG Arena: routine mana payments happen automatically, while decisions that might meaningfully affect gameplay remain under my control.

Manaforge should default to automatic mana payment, with a straightforward manual override.

**The Java gateway owns payment automation. XMage remains the sole rules authority. Unity must not implement mana rules, payment calculations, or source-selection logic.**

## 2. Current implementation — verified findings

The existing code establishes several important starting points.

### Current Manaforge infrastructure

- `GatewayCommandGate` validates authenticated commands against the viewer's current offered decision, revision, and object IDs.
- `GatewaySessionBoundary` owns current-decision admission, submission reservations, duplicate handling, and receipt state.
- `GatewaySessionBoundary.dispatch()` provides a one-time trusted enqueue callback. It does not yet execute XMage actions.
- The Java/C# protocol supports `select_mana_source`, using a current viewer-scoped `object_id`.
- `ClientSessionChannel` supports the mana-source command family and requires an active mana decision.
- `ViewerSessionHost` has outgoing APIs for perform, choose, finish, and cancel. Numeric and mana-source dispatch are not yet implemented at this host layer.
- No complete legal-mana-source enumeration, automatic source choice, or real Java-gateway/XMage payment integration has been demonstrated.

### XMage capabilities already available

The pinned engine contains functionality worth reusing:

- `ManaPool.setAutoPayment()` and `setAutoPaymentRestricted()` control automatic spending from the player's mana pool.
- `ManaUtil.tryToAutoPay()` can narrow the mana abilities available on a selected source.
- `ManaUtil.tryToAutoSelectAManaColor()` can resolve certain unambiguous color choices.
- `HumanPlayer.playMana()` and `playManaAbilities()` already implement the engine's payment interaction.
- `UserData` carries native mana-payment preferences.
- XMage checks payment restrictions, applicable effects, and whether mana is usable for the cost being paid.

These facilities do not constitute complete automatic source selection across a battlefield.

**Codex must verify the behavior and interfaces in the pinned binaries before relying on them.** Do not assume newer upstream XMage methods exist.

## 3. Architecture

The expected interaction is:

```text
Unity
  |
  | User chooses to cast a spell
  v
Java Gateway
  |
  | Validated command
  v
XMage
  |
  | Authoritative payment requirement
  v
Java Payment Coordinator
  |
  +-- Auto disabled?
  |      |
  |      +-- Expose manual payment
  |
  +-- Safe payment identifiable?
         |
         +-- YES: Submit engine-valid responses
         |         |
         |         v
         |     XMage confirms state
         |
         +-- NO: Expose manual payment
```

The payment coordinator belongs within the Java gameplay-session boundary, not the Unity presentation layer or a new rules engine.

It must operate through a narrow, engine-aware interface so the policy can be tested independently of process management, networking, and UI code.

Do not put automatic payment inside `GatewayCommandGate`, `SubmissionLedger`, a JSON parser, or the renderer. Those components have separate responsibilities.

## 4. Functional requirements

### FR-1: Payment modes

Support the following per-human-seat preferences:

**Auto — default**

- Automatically complete supported, safe mana payments.
- Use the engine's existing payment behavior wherever applicable.
- Fall back to manual input whenever the gateway cannot establish a sufficiently safe payment.
- Do not silently change other player decisions.

**Manual**

- Expose payment choices without automatically activating mana sources.
- Respect the player's explicitly selected sources and options.
- Retain XMage's authoritative legality and cost handling.

**Full Control**

- Disable bridge-initiated payment automation.
- Keep priority automation controlled separately.
- Do not automatically resolve strategic choices.

The initial integration may use a session-scoped configuration rather than adding a complete settings UI. The mode must belong to the relevant human player, not to a global singleton.

### FR-2: Safe MVP payment scope

The first implementation should concentrate on ordinary mana payments involving basic, unrestricted mana-producing abilities.

Examples of the intended supported behavior include:

- Paying `{G}` from a suitable Forest.
- Paying `{1}{U}` using a suitable combination of uncomplicated sources.
- Paying `{2}{G}` from sufficient ordinary sources.
- Using already-floating mana where XMage's payment rules and configuration permit it.
- Choosing between interchangeable sources with identical relevant engine-confirmed payment behavior.

Favor deterministic choices. Where equally valid payments exist, preserve more flexible sources when that preference can be determined from reliable engine information.

Do not introduce a custom Magic mana-cost solver. Source suitability and payment outcomes must be established through XMage facilities and verified against the pinned engine.

If safe multi-source planning cannot yet be supported, implement a narrower, demonstrably correct subset and report the unsupported cases. Do not guess.

### FR-3: Native engine integration

Before writing payment-selection code, investigate:

1. How the pinned XMage engine represents the current unpaid cost.
2. Which APIs provide currently usable mana abilities for that specific payment.
3. Whether the engine can distinguish ordinary, restricted, and strategically significant mana abilities.
4. How it determines floating mana usability and automatic spending.
5. How automatic color choices interact with the ongoing cost.
6. How the engine represents special payment methods and additional prompts.
7. Whether the selected operation can execute immediately or creates another response cycle.

Prefer extending existing Java session integration through a narrow adapter over modifying XMage internals.

Do not modify the original pinned XMage installation or weaken artifact verification.

Document the exact interfaces used, their limitations, and the pinned-version assumptions.

### FR-4: Automatic selection safety

Auto payment must not make consequential choices without explicit support and a demonstrated safety policy.

Initially fall back to manual input for cases including:

- Mana abilities that require sacrificing resources beyond ordinary tapping.
- Mana abilities with optional life payments or meaningful additional costs.
- Multiple abilities with different non-mana effects.
- Spells or effects that care about the colors or sources of mana spent.
- Restricted or conditional mana whose applicable payment cannot be reliably established.
- Costs involving X when the required X value has not already been chosen.
- Special payment mechanics such as convoke, improvise, or other nonstandard payment methods without verified support.
- Hybrid, Phyrexian, snow, alternative, or similarly specialized costs that the initial policy cannot handle safely.
- Unknown or unsupported engine payment states.

These categories are not permanently prohibited from automatic payment. They are outside the initial safe scope until their behavior is verified.

Use the engine's actual characteristics and payment constraints, not printed card text or card-name heuristics.

### FR-5: Serialized execution and stale decisions

Automatic payment must respect the same session, viewer, decision, and revision authority as manual commands.

Requirements:

- Only operate for the authenticated player's current payment decision.
- Serialize automatic and manual decision execution through the session's engine-command owner.
- Never submit an action for another player's decision.
- Never use stale game-object references.
- Prevent double submission when manual interaction and automation overlap.
- Revalidate subsequent steps after an engine response.
- Stop on replacement decisions, disconnect, cancellation, game termination, or owner shutdown.
- Do not continue an old payment sequence into a new spell or decision.

Bridge-initiated payment responses must be distinguishable internally from client-issued commands. Do not invent Unity commands or fabricate client acknowledgements for automatic actions.

### FR-6: Engine-confirmed outcomes

Successful submission is not proof of successful payment.

The coordinator must distinguish:

- Payment action submitted.
- Engine confirmed payment progress.
- Payment completed.
- Engine rejected or replaced the decision.
- Manual intervention required.
- Outcome uncertain because of a transport or lifecycle failure.

The UI must ultimately reflect the authoritative XMage state.

Never optimistically remove mana, tap lands, or resolve a spell using bridge-calculated state.

### FR-7: Manual fallback and interruption

When automatic payment cannot proceed safely:

- Stop initiating new payment actions.
- Keep or restore the current engine-provided payment decision when available.
- Notify the viewer that manual payment is required.
- Preserve valid existing actions and options.
- Do not assume already activated mana sources can be undone.
- Do not automatically retry a command with uncertain results.

Manual mode should be selectable before starting automatic source activation.

For the MVP, do not implement an artificial rollback system. Use existing engine-supported cancellation/undo behavior only where proven available.

If an automatic sequence has already performed a confirmed irreversible action, preserve that state and make subsequent choices manual rather than pretending the original state can be restored.

### FR-8: Player experience

The ultimate Unity experience should be simple:

1. The player selects a spell.
2. XMage requests the required payment.
3. The gateway handles supported payments automatically.
4. Unity updates from authoritative state.
5. If assistance is required, Unity presents the actual pending choices.

The gateway should not require a popup for ordinary successful automatic payments.

Do not build a new Unity payment interface as part of this story. Expose the minimum bounded status and decision information needed for the existing or forthcoming P3.4 controls.

Any changes to shared protocol schemas must be versioned and regenerated for Java and C# using existing tooling.

## 5. Implementation approach

### Step A — Engine capability investigation

Inspect the pinned XMage Java sources and binaries, including:

- `HumanPlayer`
- `ManaPool`
- `ManaUtil`
- `UserData`
- `PlayerImpl`
- Existing Manaforge Java bridge response handling

Record the reusable engine payment behavior and any missing interfaces.

Determine the narrowest viable approach to safe source selection.

This investigation should lead into implementation, not become an indefinite research phase.

### Step B — Add a bridge-owned payment coordinator

Introduce a small, cohesive Java payment coordinator with explicit inputs and results.

It should accept trusted engine payment context and per-seat preferences, determine whether the current request is eligible for automation, and submit decisions through an engine-facing executor.

Keep engine inspection and orchestration separate from policy selection where practical, without introducing unnecessary abstractions.

No Unity dependency, Qt dependency, Python gameplay dependency, database dependency, or renderer dependency.

### Step C — Integrate with the Java session owner

Connect the coordinator to actual payment prompts once the Java/XMage session can emit them.

Automatic payment must use the same serialized engine-decision execution boundary as manual submission.

Retain existing command deduplication, uncertainty, viewer isolation, and process ownership.

Do not bypass `GatewaySessionBoundary`'s security assumptions or duplicate its receipt authority.

### Step D — Implement conservative selection

Support straightforward, engine-validated mana payments first.

Use deterministic selection for equivalent options. If the engine does not provide enough information to establish a safe choice, require manual input.

Do not implement speculative source activation to discover whether a payment works.

### Step E — Connect preferences and fallback

Expose a per-seat auto-payment mode to the gateway's trusted session configuration.

Ensure manual payment remains available using the existing protocol command families.

Avoid expanding the public API unless the current contracts demonstrably cannot express required information.

### Step F — Real-engine acceptance

Verify that actual pinned XMage games complete representative payments.

The story cannot be considered gameplay-complete merely because dummy protocol tests pass.

## 6. Acceptance criteria

- [ ] Pinned XMage payment APIs and limitations are documented.
- [ ] Java owns the automation policy; Unity contains no mana-payment calculation.
- [ ] Auto, Manual, and Full Control payment behavior is independently configurable per human seat.
- [ ] Ordinary basic-land mana payment works in an actual XMage game.
- [ ] A supported multi-source generic/colored payment completes correctly.
- [ ] Engine-supported floating mana payment is preserved.
- [ ] Automatic payment does not activate an unverified costly or strategically significant mana ability.
- [ ] Ambiguous or unsupported payments fall back to manual interaction without guessing.
- [ ] A manually selected payment is not overridden by concurrently running automation.
- [ ] Engine decision replacement and stale revisions stop pending automation.
- [ ] Duplicate or uncertain submissions are not automatically replayed.
- [ ] Source activations and payment completion are verified from subsequent engine state, not ACKs alone.
- [ ] Player cancellation, disconnect, owner loss, and shutdown safely terminate automation.
- [ ] Hidden engine state and another seat's private information never enter the client or diagnostic logs.
- [ ] Source documents, selected printings, and unrelated Manaforge workspaces remain unchanged.
- [ ] All relevant Java/protocol CI checks pass.
- [ ] A repeatable pinned-XMage acceptance scenario succeeds without fixture-only payment simulation.

## 7. Required test coverage

Create focused Java tests for selection policy, decision lifecycle, manual fallback, and engine dispatch.

Required cases include:

| Scenario | Expected behavior |
|---|---|
| One Forest, `{G}` | Automatic payment |
| Sufficient ordinary lands, `{2}{G}` | Automatic payment if supported and verified |
| Insufficient mana | No invented or speculative payment |
| Multiple equivalent basic sources | Deterministic selection |
| Multiple strategically different choices | Manual fallback |
| Floating mana | Respects XMage's configured native behavior |
| Restricted mana | Only auto if applicability is verified |
| Costly or consequential mana ability | Manual fallback |
| Color-sensitive mana expenditure | Manual unless explicitly verified safe |
| Payment requiring an unsupported choice | Manual fallback |
| New decision after payment begins | Old automation stops |
| Repeated response or stale token | No duplicate execution |
| Disconnection after submission | Uncertain, never blindly retried |
| Seat change or owner shutdown | Automation stops and private state is cleared |
| Manual/Full Control | No bridge-initiated source activation |

Add at least one real pinned-engine scenario verifying actual source activation, payment, spell resolution, and clean process termination.

Use semantic state changes as evidence; a command being accepted is insufficient.

## 8. Explicit non-goals

This story does not require:

- A full Arena-style payment interface.
- Exhaustive optimization of all possible mana combinations.
- Reimplementing Magic's cost/payment rules.
- Changing XMage's rules engine.
- Automatic strategic decisions, targets, or optional costs.
- Automatic priority passing.
- Networked multiplayer.
- Reconnection or persistent in-progress payment recovery.
- Supporting every unusual mana ability before the MVP.
- Migrating unrelated Python, Qt, editor, database, or printer code.

## 9. Development and verification requirements

Follow Manaforge's existing Codex workflow.

1. Inspect the latest branch, roadmap, relevant code, and tests before editing. Do not assume this documented baseline is still current.
2. Reuse established boundaries and protocols rather than introducing competing systems.
3. Keep changes focused, reversible, and understandable.
4. Use focused local tests and diagnostics where useful; do not run the full application test suite locally.
5. Allow CI to run comprehensive verification and review it at the established checkpoints.
6. Do not claim that tests passed without actual evidence.
7. Preserve sanitized diagnostics. No private hands, deck contents, payment prompts, credentials, or sensitive game-state dumps in shared logs.
8. Preserve current engine pins, integrity verification, and artifact provenance.
9. Do not introduce required network downloads into normal offline gameplay.
10. Document limitations and unsupported cases explicitly. Never silently substitute payment behavior.
11. Do not mark the feature complete based only on mocks, static inspection, or synthetic session tests.
12. Do not modify unrelated components merely to make tests pass.

## 10. Completion and handoff

Codex must provide:

- Implementation summary.
- Changed files and purpose.
- Exact native XMage facilities reused.
- Supported automatic payment cases.
- Cases intentionally requiring manual payment.
- New or changed protocol fields, if any.
- Focused test results.
- Real-engine acceptance evidence and relevant CI results.
- Remaining blockers and follow-up work.
- Any owner-visible behavior that requires manual UX review.

**If Phase 2's Java/XMage session integration is still unavailable, implement and test the isolated policy only where it is genuinely useful, keep production automation disabled, and explicitly report the live-integration dependency. Do not claim an end-to-end feature is complete.**

## Definition of done

A player initiates a supported spell or ability in a real XMage game. The Java gateway safely completes an ordinary mana payment without unnecessary user interaction. XMage confirms the payment and the action progresses normally.

When automatic payment cannot be established safely, the player retains manual control.

The implementation is tested, respects viewer/session isolation, and does not duplicate Magic's rules.

**The result should make Manaforge feel smoother without making its gameplay less trustworthy.**
