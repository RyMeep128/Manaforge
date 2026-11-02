# Live Unity / Java / XMage integration

## Repeat casting and combat in Unity (0.5.197)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --combat-damage --complete-combat --loop-turn --next-turn-cast --repeat-cycle --no-capture
```

The bounded same-session continuation now offers the original creature for a
second attack after casting another creature. Separate native evidence confirms
combat entry, selection, declaration, damage and cleanup; the newly cast creature
is excluded from the attacker offer. The endpoint checks the second life decrease,
retained card identities and native source incarnation. Session history remains
bounded at 64 entries to cover the opening and 32 continuation decisions.
Full-match results and general choices remain open; visual work stays deferred.

## Cast again on the next human turn in Unity (0.5.196)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --combat-damage --complete-combat --loop-turn --next-turn-cast --no-capture
```

The next human-turn snapshot now offers native Cast spell actions on the same
session. The card selection receives a separate typed confirmation: its captured
native ability IDs must match the later ability menu, the source stays visible
in hand with unchanged guarded incarnation, and the exact accepted request must
match the queued command. This confirms entry into native casting, not resolution.

The following ability selection is confirmed through its exact native stack
instance, then an explicit priority pass is confirmed by the source's native
battlefield transition. Public graveyards remain available throughout the cast.
The final snapshot is read-only and the probe requires all three new snapshots;
a consumed decision disappearing between offers cannot be mistaken for completion.

The no-capture run checks repeated card choice, ability choice and resolution
without opening another session. The validated run delivered 14 snapshots, 26
acknowledgements, 13 confirmed receipts and zero uncertain receipts. Longer repeated Unity combats, arbitrary spell
costs/choices and full-match results remain open. Human visual review remains
deferred while gameplay work continues.

## Repeat play and combat after the turn cycle (0.5.195)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority --combat-damage --complete-combat --loop-turn --repeat-cycle
```

The Java fixture now uses a renewed native card offer to cast and resolve another
Memnite on the next human turn, then explicitly attacks with the original,
now-untapped creature and completes a second combat. The newly cast creature is
not substituted as the attacker. Resolution checks account for the existing
battlefield and require the selected source to be present. Turn-compatible
projection preserves public graveyards across casting, ability selection, stack
passes and combat.

The repeated endpoint requires a distinct new hand source on the battlefield,
retained remaining hand identities, stable original attacker incarnation, the
same turn, no extra draw or graveyard change, cleared stack/combat, original
attacker tapped again, unchanged human life and another one-point opposing life
decrease. Reports add `native_next_turn_creature_resolved` and
`native_repeated_combat_observed`. The repeat is bounded to one additional cycle.

This proves repeated native fixture play; Unity currently ends read-only after
its first turn cycle. Repeated interactive Unity casts, full-match results and
broader gameplay remain open. Human visual review remains deferred.

## Continue the Unity session through the next human turn (0.5.194)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --combat-damage --complete-combat --loop-turn --no-capture
```

The same authenticated packaged session now continues after combat cleanup,
serving engine-offered Pass priority and cleanup Discard actions until the human's
next pre-combat main phase. Each input receives typed exact-command evidence
before its receipt is confirmed and the next snapshot is sent. A discard must
move the offered card from the active human's eight-card hand into that seat's
graveyard. Invalid guards, changed source incarnation, unsupported decisions,
life changes and mismatched outcomes fail closed. The turn chain is capped at
32 inputs, with existing per-read deadlines and bounded replay retries.

The endpoint proof checks native draw, untap, retained hand identities, any cleanup
discard, stable life totals and renewed native card offers. The final Unity
snapshot is read-only: continuing another cast beyond this bounded cycle is
subsequent gameplay work. The live run completed a required discard, the AI turn
and the next human main phase with 11 snapshots, 20 acknowledgements, 10 confirmed
receipts and zero uncertain receipts, then cleared the viewer and owned roots.

`--no-capture` skips image generation while preserving gameplay checks. Human
visual review remains deferred. Full-match results, repeated interactive cycles,
human blocker selection and broader rule/choice coverage remain open.

## Continue through turn end, cleanup and the next human turn (0.5.193)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority --combat-damage --complete-combat --loop-turn
```

The Java fixture now continues beyond combat, through the opposing turn and back
to the human's next pre-combat main phase. A bounded sequence of at most 32
engine-offered decisions uses authenticated one-shot priority passes and, when
required, explicit cleanup discard actions. Discard offers require native
`GAME_TARGET` in phase `END` / step `CLEANUP`, an active human hand above seven,
and unique native candidates present in that visible hand. No prompt text or
client rule calculation selects the native decision family.

The turn projection includes public graveyards with ownership from the native
seat rows. It filters normal continuation actions to Pass priority; after the
completed cycle, it exposes actual engine-offered card actions again. Native
endpoint evidence requires the same source incarnation, an observed untap,
unchanged life totals, one own library decrement and one new hand identity,
retained undiscarded hand identities, and any accepted discards present in the
human graveyard. The actual turn counter advances through the opposing seat.

The live proof exercised a required discard and returned with another cast offer.
Reports include `native_next_human_turn_observed`, `native_own_draw_observed`,
`native_source_untapped`, `native_next_turn_actions_offered` and the observed
`native_cleanup_discard_observed` boolean. This is a Java gameplay-cycle proof;
Unity continuous turn/decision delivery and full-match results remain open.
Human visual review is deferred at the owner's direction until the gameplay loop
is complete. The next work is gameplay/session integration, not visual acceptance.

## Display native marked blocker damage in Unity (0.5.192)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --blocked-combat --blocked-damage
```

The optional fourth input offers one explicit Pass priority after the native
blocker assignment. Java confirms it with the guarded blocked-damage certificate
tracking both incarnations, then sends a fifth read-only snapshot. The public
receive boundary validates both the pass-only offer and the final blocked view.

Unity copies each blocker's marked damage into immutable snapshot values. For the
single-Ornithopter fixture it displays the actual native `0 -> 1` damage values
and verifies defender life stayed unchanged. `blocked-damage.png` captures the
result. Acceptance requires five snapshots, eight acknowledgements, four confirmed
receipts, zero uncertain receipts, known blocker names, unchanged defender life,
then viewer clearing and owned-root cleanup. This is a bounded native fixture
observation; human blocker choices, lethal combat and general combat acceptance
remain open.

## Observe native blocked damage in Java (0.5.191)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority --blocked-combat --blocked-damage
```

This Java-only continuation offers one explicit priority pass for a single
Ornithopter blocking Memnite. The private metadata query tracks both visible
battlefield objects. Typed evidence requires the same attacker and blocker
incarnations, owner/controllers and assignment; native transition into
`COMBAT_DAMAGE`; empty stack and unchanged life totals; Memnite still native 1/1
with zero damage; and the same native 0/2 Ornithopter changing from zero to one
marked damage. Unsupported powers, multiple blockers, lethal or missing objects,
stale decisions and changed metadata fail closed.

The sanitized report records `native_blocked_damage_pass_submitted` and
`native_blocker_damage_observed`. This is an observed native fixture effect,
not client-calculated damage or general combat acceptance. Unity still ends at
its blocker-name view; displaying and confirming this additional observation
there, human blocker selection and broader combat outcomes remain open. CI runs
the additional blocked-damage fixture.

## Display native AI blocker names in Unity (0.5.190)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --blocked-combat
```

The separate Memnite-versus-Ornithopter fixture now uses the packaged Unity
session. Three explicit inputs receive typed confirmations, followed by a fourth
read-only snapshot with the native AI blocker assignment. Java requires blockers
present and native `blocked` true, validates their opaque public references, and
checks the receive boundary before transmission.

Unity copies blocker names into immutable public combat values and displays the
actual native names with the assignment. Acceptance requires four snapshots,
six acknowledgements, three confirmed receipts, zero uncertain receipts, known
blocker names and a positive displayed blocker count matching native blocker
presence. The viewer then clears and owned roots exit. The result is captured in
`post-declared-priority.png`. This observes AI-owned blocking only; explicit human
blocker selection, blocked damage and general combat acceptance remain open.

## Observe native AI blockers in a separate Java fixture (0.5.189)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority --blocked-combat
```

This variant gives the AI a public all-Ornithopter deck instead of all Forests,
while retaining the human's Memnite deck. Diagnostic setup passes engine-offered
priority over AI spells through the existing stack-omitting projection. It then
uses the same explicit attacker, declaration-finish and priority commands.

Acceptance requires native blockers present and `blocked` true, with typed
post-declaration evidence binding the same attacker incarnation and defender.
Blocker IDs must refer to unique visible opposing battlefield objects. The resulting
read-only public assignment is validated by the receive boundary. Reports include
`native_blocking_fixture`, `native_blockers_observed` and
`native_blocker_projection_validated`, all true. The original unblocked decks and
stopping points are retained.

This Java-only fixture observes AI-owned blocking. It does not submit a human
blocker choice, validate blocked damage, or claim general combat acceptance.
Unity integration and human blocker selection remain subsequent work. CI includes
both blocked and unblocked fixtures.

## Display cleared combat in Unity (0.5.188)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --combat-damage --complete-combat
```

The optional fifth input is an explicit priority pass after the damage observation.
Java confirms it through the cleanup certificate and sends a sixth read-only
snapshot at native post-combat main, with no combat assignment. The priority chain
is capped at three explicit follow-ups and the attacker session has a bounded
six-minute deadline to accommodate five interactive choices.

Unity retains the defender's opaque public ID and copies per-player life totals
into immutable snapshot values. The cleared-combat view must preserve the actual
post-damage defender life. Acceptance requires six snapshots, ten acknowledgements,
five confirmed receipts, zero uncertain receipts, empty combat and unchanged life,
then viewer clearing and owned-root cleanup. `combat-cleanup.png` captures this
observation. This completes the bounded unblocked fixture in Unity; full games,
blocking, lethal outcomes, complex choices, product launch and formal gates remain
open. Shorter probes retain their existing stopping points.

## Observe combat cleanup in the Java fixture (0.5.187)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority --combat-damage --complete-combat
```

After the native combat-damage observation, this Java-only continuation submits
one explicit priority pass. The pinned engine resumes human priority directly in
`POSTCOMBAT_MAIN`; no intervening end-combat priority prompt is fabricated.
Typed evidence requires the exact accepted response and later guarded priority,
a transition from native `COMBAT_DAMAGE` to post-combat main on the same turn,
cleared combat, unchanged source incarnation and unchanged two-seat life totals.
Unsupported, stale, blocked or altered-life states fail closed.

The sanitized report records `native_postcombat_main_observed` and
`native_combat_cleared`. This closes the bounded unblocked Java combat fixture,
not a complete game or general combat acceptance. Unity still ends at its damage
observation; cleanup integration there, blocking, lethal outcomes, complex choices
and authoritative results remain open. CI includes the cleanup continuation.

## Confirm and display the damage-window pass in Unity (0.5.185)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority --combat-damage
```

The optional fourth input offers another explicit Pass priority after the prior
combat observation. Java confirms it only through the bounded native combat-damage
step/life-change certificate, then sends a fifth read-only snapshot. The existing
bounded priority continuation handles both passes; no further input is offered.

Unity copies the defender's life total into its immutable public combat view and
displays the actual before/after values from the mounted snapshots. Acceptance
requires five snapshots, eight acknowledgements, four confirmed receipts, zero
uncertain receipts, a one-point displayed life decrease, a cleared viewer and
reaped owned processes. `combat-damage.png` captures the observation. Blocked,
lethal and altered-power outcomes remain unsupported; this public 1/1 fixture is
not general combat acceptance or a complete match.

## Observe the fixture's native combat-damage life change (0.5.184)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority --combat-damage
```

This Java-only continuation submits one additional explicit priority pass through
the authenticated fixture. Its typed pass certificate requires the prior guarded
combat evidence, an unchanged unblocked assignment and source incarnation, empty
stack, the same turn, a native transition into `COMBAT_DAMAGE`, and exactly one
life lost by the opposing defender while the viewer's life stays unchanged.
The visible fixture source must be Memnite with native 1/1 characteristics.

The report records `native_combat_damage_pass_submitted` and
`native_combat_damage_life_change_observed`. This proves a bounded native step and
life-total observation in the public two-seat fixture, not a general damage or
combat implementation. Blocked, lethal, altered-power and unsupported outcomes
fail closed. Unity still ends after the prior pass; displaying and confirming
this additional observation there remains subsequent work. CI runs this fixture.

## Submit post-declaration priority from Unity (0.5.183)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack --declared-priority
```

After confirming the attacker choice and Finish attacks, Unity offers one native
Pass priority on the same authenticated session. The existing typed priority
confirmation requires exact queued-command evidence from the guarded Java
post-declaration validator. Java then sends a fourth read-only combat snapshot.

The narrow result projection preserves the single selected attacker and opposing
defender, and maps any unique visible opposing battlefield blockers to opaque
IDs. Earlier selection/declaration projections still reject blockers. Unity
refreshes its assignment summary for each revision, displays native blocker
counts when present, and captures `post-declared-priority.png` after mounting the
actual result revision. Acceptance requires four snapshots, six acknowledgements,
three confirmed receipts, zero uncertain receipts, matching native/UI blocker
presence, a cleared viewer and reaped owned processes. No damage is inferred and
no fourth input is sent. Existing shorter combat probes remain available.

## Observe one post-declaration pass in Java (0.5.182)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack --declared-priority
```

This Java-only continuation offers one explicit Pass priority after the nonempty
attack declaration. Other playable actions are removed from both the public
snapshot and native token map. The exact accepted response is correlated with a
later guarded priority prompt, the unchanged attacker incarnation, the same
attacker/defender and turn, and empty stack. Any reported blockers must be unique
visible battlefield objects controlled by the opposing defender. Unsupported or
mismatched states fail closed; no further responses are sent.

The sanitized report includes `native_declared_priority_submitted`,
`native_declared_priority_observed` and the observed `native_blockers_observed`
boolean. A blocker assignment is an engine observation, not proof of damage or
a reconstructed combat rule. Unity still ends at its read-only post-declaration
priority snapshot. CI exercises this additional fixture continuation.

## Finish the selected attack from Unity (0.5.181)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata --finish-selected-attack
```

The optional continuation presents the verified attacker assignment with one
explicit Finish attacks button. The same authenticated session submits that
native response once. A separate typed declaration certificate must match the
queued command and request ID before its receipt is confirmed. Null, mismatched,
replayed and stale submissions remain rejected or reuse their existing receipt.

After guarded native priority resumes with the same source incarnation and combat
group, Java sends a third read-only snapshot. Unity waits for its actual revision,
displays the retained assignment with declaration finished, and captures
`declared-attack.png`. Acceptance requires three snapshots, four acknowledgements,
two confirmed receipts, zero uncertain receipts, both assignment observations,
a cleared viewer and reaped owned processes. No priority input, blocking or damage
is performed. The default attacker-selection probe still ends with declaration open.

## Finish the selected attack in the Java fixture (0.5.180)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker --finish-selected-attack
```

After selecting the resolved Memnite, the authenticated Java fixture exposes only
Finish attacks for the nonempty declaration and sends that explicit response once.
A separate immutable declared-attack certificate requires the exact accepted
boolean-false command and request ID, a later guarded priority prompt, unchanged
source incarnation and turn, and the same single-attacker combat group and opposing
defender. Empty combat, altered assignment, stack contents, stale decisions and
mismatched guards fail closed. This does not reuse the empty-combat finish proof.

The sanitized report distinguishes `native_selected_attack_finished` and
`native_declared_attack_observed`, with `native_attack_selection_open` false.
The native priority window is observed without further inputs. Unity still ends
after its read-only selected assignment; nonempty Finish attacks integration,
blocking and damage remain subsequent work. CI runs this additional Java fixture.

## Display the selected attack assignment (0.5.179)

The `--select-attacker --native-metadata` Unity probe now sends a second,
read-only snapshot after confirming the exact attacker choice. The narrow Java
projection accepts one visible controlled battlefield attacker, no blockers, an
unblocked native group and a known opposing defender. It maps both references
to opaque public IDs and strips decision/action authority. Unsupported combat
shapes fail closed and old action tokens remain invalid.

Unity projects immutable attacker/defender display names from the received public
snapshot. After the actual revision is mounted, it displays the assignment,
captures `attack-assignment.png`, and reports `attack_assignment_presented`.
Acceptance requires two snapshots, one confirmed receipt, zero uncertain receipts
and a cleared viewer. Declaration remains open; no finish, blocking or damage
is inferred from the assignment.

## Confirm the exact attacker choice (0.5.178)

The existing `--select-attacker --native-metadata` Unity probe now receives a
confirmed receipt after Java verifies the native assignment. An immutable typed
certificate retains the exact submitted native command. Session confirmation
requires the same request ID and full command as the queued input; null,
wrong-command and wrong-request evidence fail closed. Duplicate delivery returns
the confirmed receipt without another native enqueue, and disconnect retains it.

The certificate is issued only through the guarded attacker-selection validator:
same source incarnation, accepted object response, later attacker prompt and
matching native combat assignment. Acceptance requires one confirmed and zero
uncertain receipts. Declaration remains open. No assignment snapshot is sent to
Unity yet; blocking, damage and finishing a nonempty attack remain subsequent work.

## Submit the attacker choice from Unity (0.5.177)

```powershell
python tools/check_play_unity_live.py --select-attacker --native-metadata
```

After diagnostic setup, the packaged player presents the native candidate through
its existing decision action panel. The acceptance script invokes the mounted
Select attacker button. Java submits the opaque action once and requires the
same guarded native assignment evidence as the Java fixture. The probe accepts
one snapshot, two acknowledgements, zero confirmed receipts and one uncertain
receipt, then clears the viewer and reaps its owned processes.

The gateway intentionally retains an uncertain receipt: attacker-selection evidence
has not yet been added as a typed session confirmation. No assignment snapshot
is sent back to Unity. Declaration remains open; finishing a nonempty attack,
blocking and damage are subsequent work. Finish attacks remains a separate probe.

## Explicit attacker choice in the Java fixture (0.5.176)

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --select-attacker
```

The authenticated Java fixture exposes opaque attacker actions from the native
candidate list and submits one explicit object choice for the resolved Memnite.
Guarded evidence requires the same source incarnation, matching accepted request,
a later non-priority attacker prompt, one native combat group containing that
source, no blockers, and a known opposing defender. The pinned engine assigns
the sole defender itself. Duplicate delivery reuses the receipt without another
native submission. Public reports contain only sanitized booleans.

Declaration remains open. This slice does not finish the attack, integrate attacker
selection into Unity, or prove blocking or damage. The existing Finish attacks
probe retains its separate empty-combat behavior. CI runs both fixture paths.

## Confirm the post-combat pass and display its next state (0.5.175)

The existing `--finish-attacks --native-metadata --combat-priority` probe now
confirms its second input through guarded native phase-transition evidence:

```powershell
python tools/check_play_unity_live.py --finish-attacks --native-metadata --combat-priority
```

The finish evidence retains the native game/viewer/source incarnation. A pass
certificate requires that source unchanged in both guarded battlefield views,
empty combat/stack, real priority windows before/after, the exact accepted
boolean-false response and request ID, matching native cycles and a later native
decision. Native turn/phase/step must change; a newer cycle alone is insufficient.
Wrong acceptance, priority guards, incarnation, viewer or unsupported prompts
fail closed. No phase-order rules are reconstructed.

After confirmation, the same session sends a third snapshot with no decision or
actions. Unity mounts the actual revision, captures `combat-priority-result.png`,
then clears normally. Acceptance now requires three snapshots, four acknowledgements,
two confirmed receipts, no uncertain receipts, native unity_combat_priority_confirmed
and combat_priority_result_presented evidence. The default combat probe remains
the two-snapshot read-only path. No further action or full combat loop is enabled.

Validation: Windows player build, the real two-input combat/phase probe, screenshot
inspection and normal viewer/process cleanup passed. 78 focused Unity receipt/
channel tests and Java protocol preflight passed, including 345 projection/
correlation/privacy checks. Session tests cover pending rejection before proof,
late uncertainty reconciliation, idempotent confirmation, cached confirmed retries
without native replay and receipt retention after the new frame/disconnect.
Default packaged combat and Java-only attacker-finish regressions passed. Lint
and formatting passed; no full application suite ran. New CI evidence remains
pending; next scheduled check: .177.

## Explicit priority input after confirmed combat finish (0.5.174)

An opt-in continuation admits one native priority pass after confirmed Finish attacks:

```powershell
python tools/check_play_unity_live.py --finish-attacks --native-metadata --combat-priority
```

The verified finish result carries a fresh native priority offer on the same
authenticated socket and ledger. A separate typed constructor permits only a
priority decision with one pass action; the default constructor still requires
a read-only snapshot. Unity waits for the exact new revision and enabled offer,
then the acceptance script invokes the mounted Pass priority button. Interactive
mode requires both choices explicitly. Attacker, defender and blocking selection
remain unsupported.

The finish receipt stays confirmed. The subsequent pass is submitted once, then
uncertain after native acceptance/advancement; the probe stops there. Acceptance
requires two snapshots, four acknowledgements, one confirmed and one uncertain
receipt, combat_priority_action_presented and native
unity_combat_priority_submitted evidence. Without --combat-priority, the existing
second snapshot remains read-only. Overall/action deadlines and bounded input
retries remain in force; this does not establish continuous combat/full-game
acceptance.

Validation: Windows player build, 49 focused Unity PlayMode host/decision/dispatch
checks and the real two-input combat probe passed with screenshot inspection and
normal viewer/process cleanup. Java protocol preflight passed with 332 projection/
correlation/privacy checks. Authenticated-session tests cover fresh post-finish
admission, exact native pass binding, duplicate suppression, retention of both
receipts, and rejection of new work while the pass remains uncertain even after
looking up the old confirmed finish receipt. Default read-only combat and existing
three-command phase regressions passed. Three focused Python provisioning checks,
CLI guards, lint and formatting passed. No full application suite ran.

Scheduled CI checkpoint: .173 [protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41364737466),
[desktop preview](https://github.com/RyMeep128/Manaforge/actions/runs/41364737445)
and feedback relay passed. Its live-opening and Tests jobs were still running
and are deferred. .171/.172 live/preview and .172 protocol passed; their Tests
were cancelled. The deferred .170 live job passed and Tests was cancelled.
New .174 CI evidence remains pending. Next scheduled check: .177.

## Read-only priority state after confirmed combat finish (0.5.173)

The existing packaged `--finish-attacks --native-metadata` probe now delivers a
second snapshot after the confirmed finish receipt, on the same authenticated
connection and receipt ledger. It projects the actual subsequent guarded native
priority state with no decision or actions and invalidates old command tokens.
The endpoint accepts only a typed verified attack result; an actionable result
snapshot is rejected, and normal session schema/binding checks precede delivery.

Unity waits for the snapshot's actual projected revision to mount, removes stale
inspection buttons, captures `combat-result.png`, then clears normally. Acceptance
requires two snapshots, one confirmed receipt, no uncertain receipts and
post_combat_priority_presented evidence. The confirmed receipt survives the new
frame; new stale attack requests cannot enqueue native work, while a retry of the
original command still gets its cached confirmed receipt. This displays the next
state without enabling further combat or priority commands.

Validation: Windows player build, the real two-snapshot Unity/XMage combat probe,
screenshot inspection and normal owned cleanup passed. 49 focused Unity PlayMode
host/decision-binding/dispatch tests and Java protocol preflight passed, including
332 projection/correlation/privacy checks. Authenticated-session tests cover
read-only result enforcement, stale-command rejection, cached confirmed retries
without native replay and receipt retention on disconnect. The existing packaged
three-command phase regression also passed. Lint and formatting passed; no full
application suite ran. New CI evidence is pending; next scheduled check: .174.

## Correlated Finish attacks receipt (0.5.172)

The existing packaged `--finish-attacks --native-metadata` probe now emits
submitted then confirmed for its exact empty attack-selection finish response.
Private immutable AttackFinishEvidence binds the queued native command and
request ID to a genuine human attacker-selection prompt, the offered source,
native response acceptance, and a later guarded priority window. Both guarded
views must retain the same visible controlled source incarnation, with that source
absent from hand and with empty combat/stack. Wrong actor/game/viewer,
acceptance, decision/cycle, candidate identity or incarnation fails closed.
No phase-order rules or success from transport alone are inferred.

The authenticated session checks the evidence against its private queued command
before settling the receipt. The shared endpoint now uses typed ability or attack
evidence; only ability evidence can enter the existing ability/priority
continuation. Ordinary choices without evidence retain uncertainty. Unity requires
one received confirmed receipt and zero uncertain receipts, then clears. Native
evidence adds unity_attack_finish_confirmed. The Java-only diagnostic still does
not claim a confirmed Unity receipt.

Validation: Windows player build, the real packaged native combat probe and
screenshot inspection passed with normal viewer/process cleanup. 78 focused Unity
receipt-tracker/channel tests and Java protocol preflight passed, including 332
projection/correlation/privacy checks. Authenticated-session tests cover wrong or
missing proof, late uncertainty reconciliation, idempotent confirmation, cached
confirmed retries without native replay and confirmation retained on disconnect.
The packaged three-command phase and Java-only attacker-finish regressions passed.
Lint and formatting passed; no full application suite ran.

This settles only this fixture's empty attacker-selection completion. Attacker
and defender selection, blocking, continuous combat and natural match completion
remain open. New CI evidence is pending; next scheduled check remains .174.

## Packaged explicit Finish attacks choice (0.5.171)

Unity's existing decision panel can now mount the actual native attacker-selection
finish offer:

```powershell
python tools/check_play_unity_live.py --finish-attacks --native-metadata
```

Add `--interactive` for manual input. Public-deck pregame, casting, resolution and
priority passing run as explicit diagnostic setup before Unity connects. The
gateway waits until the earlier cast source is actually offered as an attacker,
then opens one authenticated Unity session with the existing guarded finish-only
projection. Unity shows Select attackers / Finish attacks, retains inspection,
and submits through the existing command dispatcher. The scripted acceptance
invokes that actual mounted button; the interactive route waits for the user.

Java requires the native boolean-false response, native acceptance, empty combat
and a subsequent guarded priority window. The finish receipt remains submitted
then uncertain. Unity requires zero confirmed receipts and one uncertain receipt,
clears the viewer and exits. Sanitized evidence adds attack_finish_presented and
unity_attack_finish_submitted, while accurately distinguishing Java diagnostic
casting/resolution from Unity ability input. No native IDs or candidate lists are
added to reports. Attacker/defender selection, blocking, combat confirmation and
continuous Unity combat remain open; no automatic combat policy is enabled in
product gameplay.

Validation: Windows player build, 42 focused Unity PlayMode decision-binding and
dispatch checks, and the packaged real-engine combat choice passed. Screenshot
inspection confirmed the native prompt and Finish attacks button; owned cleanup
passed. Java protocol/socket preflight passed with 310 projection/privacy/binding
checks. The existing packaged three-command phase probe and Java-only attacker
finish regression passed. Three focused Python provisioning checks, CLI guards,
lint and formatting passed. No full application suite ran.

Scheduled CI checkpoint: .170 [protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41363354451),
[desktop preview](https://github.com/RyMeep128/Manaforge/actions/runs/41363354580)
and feedback relay passed. Its live-opening and general Tests jobs were running
and are deferred. .168/.169 live/protocol/preview passed; their Tests were
cancelled, as was the deferred .167 Tests run. New .171 CI evidence remains
pending. Next scheduled check: .174.

## Native attacker-selection finish port (0.5.170)

Java can now project the explicit finish response for an actual native attacker
selection. The opt-in Java-only proof reaches an attack-capable turn with the
public Memnite/Forest decks:

```powershell
python tools/check_play_live_opening.py --first-creature --native-metadata --finish-attacks --output Mtg_Projects/mtg_play_unity/Artifacts/CombatFinish/report.json
```

The projection requires GAME_SELECT, is_priority=false, the native attackers
array, the human active player, empty current combat/stack, and bounded unique
candidates already visible and controlled on that player's battlefield. It offers
only Finish attacks, mapped to the existing native boolean-false response.
Attacker/defender selection and blocker prompts are not exposed. Missing or hidden
candidate information, foreign candidates, stale cycles and other prompt families
fail closed and invalidate the previous tokens. The ordinary projection still
rejects combat prompts. Actions remain explicitly incomplete.

The diagnostic uses bounded explicit priority passing and empty attack selections
as fixture policy until the physical source of the earlier cast is actually offered
as an attacker. It then submits Finish attacks through the authenticated session
boundary, requires native acceptance, empty combat and a subsequent guarded native
priority window. No rules or attacker legality are recomputed. The report adds
native_attack_source_offered, native_empty_attack_submitted and
native_combat_advanced; no native IDs, candidates or hidden cards are uploaded.
The existing live Java CI workflow now runs this probe and uploads its sanitized
report. Its receipts remain conservative; this does not confirm arbitrary combat
commands or add automatic combat choices to Unity.

Validation: the actual pinned-engine cast/resolution/attacker-finish probe passed
with duplicate suppression and normal owned-root cleanup. Java protocol preflight
passed with 310 projection/privacy/binding checks, including foreign/hidden/unknown
candidates, wrong actor/family, stale cycles, stack/combat rejection and native
boolean mapping. Authenticated socket tests require one native finish enqueue and
cached duplicate receipts. The existing packaged Unity three-command phase probe
also passed. Three focused Python provisioning checks, CLI guards, lint and
formatting passed. No C# changes, Unity rebuild or full application suite ran.

This advances P2.3 combat decision coverage. Next: mount the real finish offer in
Unity's existing decision panel with explicit user input; do not carry the Java
diagnostic's fixture policy into product gameplay. New CI evidence remains pending;
next scheduled check: .171.

## Confirm the post-resolution pass and show native phase state (0.5.169)

The existing `--post-resolution-pass` option now verifies that final pass and
delivers a fourth, read-only snapshot on the same authenticated session:

```powershell
python tools/check_play_unity_live.py --creature-ability --native-metadata --continue-priority --observe-resolution --post-resolution-pass
```

In this owned, serialized public fixture, private phase evidence requires the
exact accepted boolean-false response for the offered native game/decision and
request ID; native priority open before and after; a later native priority
decision with matching cycles; empty stacks and the exact existing battlefield
source incarnation in both guarded views; and a changed native turn, phase or
step. A newer cycle alone, an unchanged phase/step, rewind, missing phase fields,
wrong acceptance or changed incarnation cannot confirm the pass. XMage determines
the transition; no Magic phase-order rules are implemented in the gateway.

After confirmation, Unity mounts the fourth snapshot without decision/actions,
captures `phase.png` and clears. Acceptance requires four snapshots, six
acknowledgements, three received confirmed receipts, no uncertain receipts and
unity_post_resolution_priority_confirmed native evidence. The ordinary
continuation without this correlated phase proof retains its uncertain outcome.
This does not enable another action, a complete combat loop or natural-match
acceptance. The next slice can use the reconciled phase boundary for subsequent
engine-offered input.

Validation: the Windows player build and real three-command Unity/XMage phase
probe passed with screenshot inspection and normal viewer/process cleanup.
78 focused Unity receipt-tracker/channel tests and Java protocol preflight passed,
including 271 projection/correlation/privacy checks. Authenticated-session tests
verify pending rejection before phase proof, late uncertainty reconciliation,
duplicate confirmation/receipt reuse without native replay and confirmed state
retained on disconnect. The uncertainty-fallback Unity probe and Java-only native
metadata cast/resolution regression passed. Three focused Python provisioning
checks, lint and formatting passed. No full application suite ran.
New CI evidence is pending; next scheduled check remains .171.

## Admit a post-resolution Unity priority pass (0.5.168)

The opt-in fixture can now admit a third command after the casting choice and
correlated pass are confirmed:

```powershell
python tools/check_play_unity_live.py --creature-ability --native-metadata --continue-priority --observe-resolution --post-resolution-pass
```

The verified battlefield snapshot carries the actual next native priority
decision with fresh revision/action tokens. This fixed all-Memnite human fixture
exposes only Pass priority, with actions_complete=false; it does not claim a
complete legal-action surface. Unity waits for the new frame and enabled engine
offer, then the scripted diagnostic invokes the actual mounted button. Add
`--interactive` to choose all three inputs manually. Without the final flag, the
previous observation snapshot remains read-only.

The same authenticated socket and ledger persist across all three commands.
The final pass emits submitted then uncertain after native acceptance and
advancement; no further decision is admitted. The probe requires three snapshots,
six acknowledgements, two confirmed receipts, one uncertain receipt and native
unity_post_resolution_priority_submitted evidence. Continuation is capped at two
priority stages, with bounded input retries and finite overall/action timeouts.
No mana/combat/general casting or full-game acceptance is claimed.

Validation: Windows player build, 42 focused Unity PlayMode decision-binding and
dispatch checks, and the real three-command Unity/XMage probe passed. Screenshot
review showed the new Pass priority offer; viewer/process cleanup passed. Java
protocol preflight passed, including 258 projection/correlation/privacy checks
and authenticated-session tests for fresh post-confirmation admission, one native
enqueue, duplicate suppression and rejection of a fourth command while the final
pass is uncertain. The prior read-only Unity path and Java-only native-metadata
cast/resolution regressions passed. Three focused Python provisioning checks,
lint and formatting passed. No full application suite ran.

Scheduled CI checkpoint: .167 [protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41361255849),
[live opening](https://github.com/RyMeep128/Manaforge/actions/runs/41361255963),
[desktop preview](https://github.com/RyMeep128/Manaforge/actions/runs/41361255630)
and feedback relay passed; Tests was still running and is deferred. .164–.166
live/protocol/preview passed; their general Tests runs were cancelled. New .168
CI evidence remains pending. Next scheduled check: .171.

## Correlated priority-pass confirmation (0.5.167)

The `--creature-ability --native-metadata --continue-priority --observe-resolution`
fixture now confirms its exact priority pass after the guarded battlefield
transition. This is deliberately scoped to the serialized public Memnite slice.
It is not a general rule that engine advancement or an empty stack confirms a pass.

Private PriorityEvidence requires the original exact stack spell, source counter
and selected ability; an actual native priority prompt with guarded priority_open;
the exact boolean-false response for that game/decision; native response_sent
acceptance with the same request ID; the verified next-incarnation battlefield
transition; and a later native priority prompt with matching guarded cycle and
priority_open. Evidence is immutable and bound to the queued native command.
Only then can the session settle that command's receipt as confirmed. Without
this evidence, the ordinary continuation still emits uncertainty.

Unity's sanitized evidence now requires two received confirmed receipts, and the
native report adds unity_followup_priority_confirmed. The third snapshot remains
read-only: this increment settles the outstanding pass without enabling broader
actions or claiming full-game acceptance. No raw native IDs or metadata enter
Unity. The next slice can admit the next action after this settled receipt.

Validation: Windows player build and the real Unity/XMage metadata/transition
probe passed, including two confirmed receipts, screenshot review and normal
viewer/process cleanup. 78 focused Unity receipt-tracker/channel tests passed.
Java protocol preflight passed, including 258 projection/correlation/privacy
checks and authenticated-session checks for wrong evidence, late uncertainty
reconciliation, idempotent confirmation, cached duplicate receipts, no duplicate
enqueue and confirmation retained on disconnect. Negative evidence covers native
acceptance, request IDs, priority guards, decision/cycle, stack identity and source
incarnation mismatches. The no-observation Unity continuation and Java-only
metadata cast/resolution regressions passed. No full application suite ran.
CI evidence is pending; next scheduled check remains .168.

## Read-only native battlefield transition in Unity (0.5.166)

The two-choice slice can now observe the exact spell source reaching the battlefield
after the submitted priority pass, then display a third, read-only snapshot:

```powershell
python tools/check_play_unity_live.py --creature-ability --native-metadata --continue-priority --observe-resolution
```

The immutable ability evidence retains the guarded stack-source counter and
cycle. Observation requires the same native game/viewer, empty stack, source
absent from hand, exactly one visible source on the human battlefield, matching
guarded owner/controller and exactly the next source incarnation. Names/counts
alone cannot satisfy it. Missing or skipped transitions fail closed. Private
source identifiers and metadata remain Java-only.

The existing projection handles empty-stack priority state, removes every action
and the decision, and invalidates command tokens. The ledger's pass receipt stays
uncertain; observing a board does not settle it or permit another command. Unity
waits for the actual projected revision to be mounted, rather than assuming that
snapshot counts equal revisions. It captures `battlefield.png` with no action
buttons, then clears normally. The report requires
unity_battlefield_transition_observed and battlefield_observation_presented with
three snapshots. The broader creature_resolved/full-game acceptance flag remains
unchanged; this is an exact state observation in the public Memnite fixture.

Validation: the Windows player build and 49 focused Unity PlayMode session,
decision-binding and dispatch checks passed. The packaged real-engine transition
passed with screenshot inspection, three snapshots, four acknowledgements and
normal viewer/process cleanup. Focused Java protocol preflight passed, including
241 projection/correlation/privacy checks and an authenticated-session check that
the read-only update leaves the pass uncertain. Negative observations cover
wrong source/game/viewer, hidden cards, stale metadata, skipped incarnations,
duplicate sources and a nonempty stack. Previous two-choice Unity and Java-only
metadata cast/resolution regressions passed. Three focused Python provisioning
checks, lint and formatting passed. No full application suite ran.
CI evidence is pending; next scheduled check remains .168.

## Next Unity priority on the same authenticated session (0.5.165)

The opt-in two-choice slice continues from the confirmed casting ability to one
real priority pass, using the same authenticated socket, session and receipt ledger:

```powershell
python tools/check_play_unity_live.py --creature-ability --native-metadata --continue-priority
```

Add `--interactive` to choose both buttons manually. The second snapshot comes
from the next native priority prompt through the existing pass-only projection.
It uses a newer revision and fresh decision/action tokens; stack contents remain
explicitly unsupported. Unity replaces the old decision, clears stale inspection
buttons, displays Pass priority and submits through its existing dispatcher.
The scripted diagnostic invokes the actual mounted buttons and captures
`priority.png`. Acceptance requires two snapshots, a presented follow-up,
four acknowledgements, native priority submission and final viewer/process cleanup.

Only the exact casting-ability receipt is confirmed. The subsequent pass is
submitted then uncertain after native acceptance/advancement, and the probe ends.
It does not claim resolved priority semantics, creature resolution or a full game.
Continuation requires metadata and verified ability evidence. Admission retains
pending-command, stale-token and duplicate-receipt guards. Duplicate/stale input
is bounded to eight attempts; both choices and the owned session have finite
timeouts. Cancellation is checked again before either native submission.

Validation: 42 focused Unity PlayMode decision-binding/command-dispatch checks
passed, the Windows player build passed, and the packaged real-engine two-choice
slice passed with screenshot inspection. Focused Java protocol checks cover
pending follow-up rejection, confirmed receipt reuse, stale ability rejection,
fresh pass admission and no duplicate enqueue. Single-choice Unity metadata and
Java-only metadata cast/resolution regressions also passed. Three focused Python
provisioning checks, lint and formatting passed. No full application suite ran.

Scheduled CI checkpoint: .164 [protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41359399966),
[desktop preview](https://github.com/RyMeep128/Manaforge/actions/runs/41359399940)
and feedback relay passed. Its Tests and live-opening jobs were still running
and are deferred. .163 live-opening/desktop preview passed; Tests was cancelled.
New .165 CI evidence remains pending. Next check: .168.

## Confirm the exact Unity casting-ability receipt (0.5.164)

The opt-in `--creature-ability --native-metadata` probe now emits submitted then
confirmed for its one casting-ability choice. An immutable private AbilityEvidence
can be created only when the pre-choice source/offer, native game/decision,
selected ability and later guarded stack-instance metadata correlate. The session
also requires that evidence to match its exact queued native command, including
the public command's request ID. Native transport acceptance and engine advancement
alone still cannot confirm anything. No native evidence is sent to Unity.

Confirmation means that ability selection produced the exact observed stack
spell; it does not mean spell resolution or match completion. The sanitized
probe adds unity_casting_ability_confirmed. Without metadata, the existing path
still emits uncertainty. Duplicate commands reuse their confirmed receipt without
another native enqueue, and disconnect does not downgrade a confirmed receipt.
The source-card click remains diagnostic setup, outside this Unity receipt.

This advances P2.3/P4.2. The probe still clears after its single choice. The next
step is projecting and admitting the next real priority decision on the same
authenticated session after this reconciled outcome. Full stack presentation,
mana, combat and natural match completion remain open.

Validation: real packaged Unity/XMage probes passed with and without metadata;
the metadata run required exact-instance confirmation and both cleared normally.
The Java-only metadata cast/stack/resolution regression passed. Focused Java
protocol preflight passed, including 224 projection/correlation checks and
authenticated-session checks for mismatched evidence, duplicate confirmation,
cached confirmed receipts, no duplicate enqueue and confirmed disconnect state.
Three focused Python provisioning tests, lint and formatting passed. Existing
Unity player reused; no C# changes, rebuild or full application suite.
CI evidence is pending; next scheduled review: .165.

## Exact native spell-instance evidence from Unity (0.5.163)

The packaged casting-ability probe can now use the guarded Java metadata channel:

```powershell
python tools/check_play_unity_live.py --creature-ability --native-metadata
```

The Java gateway captures the native ability selected through Unity and verifies
the resulting stack spell against the original source, source incarnation and
selected ability using the existing NativeCastCorrelation checks. It also checks
that restricted metadata omits the private incarnation/ability fields. The
sanitized report requires native_stack_source_matched and
native_cast_instance_matched; native IDs and metadata do not enter Unity or the
report. Metadata provisioning is shared with the Java-only proof, remains a
one-time parent operation, clears its key even on failure and leaves subsequent
queries entirely Java-to-Java. CI watches the shared helper as a live-proof input.

This advances P2/P4's outcome-correlation prerequisite. It does not yet reconcile
the submission ledger: receipts remain uncertain, the Unity probe still ends
after one choice and creature_resolved remains false. Continuous Unity priority,
stack translation and natural match completion remain open. Next implementation:
use exact correlated evidence to settle the appropriate receipt before admitting
a subsequent authenticated Unity decision; preserve rejection/duplicate guards.

Validation: the packaged Unity choice with exact source/instance metadata and
normal cleanup passed using the existing player (no C# change or rebuild).
The existing Java-only native-metadata cast/stack/resolution proof also passed.
Focused Java protocol preflight passed, including 211 projection/privacy checks,
28 metadata-channel checks and authenticated socket/session tests. Three focused
Python provisioning failure/cleanup tests, lint and formatting passed; invalid
CLI flag combinations reject before launch. No full application suite ran.
CI remains pending for this change; next scheduled check: .165.

## Clear opening focus when cards detach (0.5.162)

Removing a mounted opening card now clears its hover/focus references and
resets any raised transform immediately. If a different card still has keyboard
focus, removing the hovered card restores that emphasis. Clearing the hand does
not restore removed cards. Disposal unregisters the additional detach callback.

Validation: 25 focused opening-focus/fan EditMode checks passed with graphics,
including hovered-card removal, keyboard-focus fallback and whole-hand clearing.
No packaged visual acceptance or full-suite run is claimed.

Scheduled CI checkpoint: latest pushed .157 [Tests](https://github.com/RyMeep128/Manaforge/actions/runs/41325988319),
[desktop preview](https://github.com/RyMeep128/Manaforge/actions/runs/41325988279)
and feedback relay still show success. .158–.162 remain local, with no CI runs.
Next scheduled check: .165.

## Raised-card bounds after resize (0.5.161)

The opening scene now refreshes the active card's horizontal bounds each frame.
The correction uses its actual transformed bounds and converts the adjustment
into hand-local coordinates. A narrowed viewport no longer leaves a raised
edge card at its old offset; cards wider than the viewport are centered.
This changes presentation only and does not submit an engine command.

Validation: 24 focused opening-focus/fan EditMode checks passed with graphics,
including a raised right-edge card during a 1000-to-600-pixel resize, viewport
containment, a stable repeated correction and offset reset on blur/clear.
No packaged visual acceptance or full-suite run is claimed. CI next: .162.

## Stable opening-hand resize layout (0.5.160)

Opening-hand relayout now uses the focus controller's original card order.
Previously, bringing a card to the front also moved it to the last layout slot
when viewport width or artwork readiness triggered another layout pass. Explicit
layout order keeps card positions stable without undoing the raised drawing
order or focus emphasis. Detached cards are not restyled.

Validation: 23 focused opening-focus/fan EditMode checks passed with graphics,
including a mounted resize while the first card is raised, expected positions,
retained enlargement and restoration of sibling order. No packaged visual
acceptance or full-suite run is claimed. Next scheduled CI check: .162.

## Stable opening-hand Tab order (0.5.159)

Opening cards now receive explicit Tab indices in their original fan order.
Raising a hovered or focused card changes drawing order without changing its
keyboard traversal index. Disposal restores each card's original focusability
and Tab index, including previously excluded cards.

Validation: 22 focused opening-focus/fan EditMode checks passed with graphics.
The regression checks raising, traversal indices and restoration. The mounted
focus-event test requires graphics and explicitly skips on null-device runners.
No packaged visual acceptance or full-suite run is claimed.

Scheduled CI checkpoint: latest pushed .157 [Tests](https://github.com/RyMeep128/Manaforge/actions/runs/41325988319),
[desktop preview](https://github.com/RyMeep128/Manaforge/actions/runs/41325988279)
and feedback relay passed. .156 Tests was cancelled; its preview passed.
.158/.159 changes remain local and have no CI evidence. Next check: .162.

## Opening-hand keyboard focus retention (0.5.158)

Pointer hover now temporarily takes precedence over keyboard focus. Leaving the
hovered card restores enlargement to the keyboard-focused card; moving the
pointer off that focused card no longer drops its emphasis. Blur still clears
emphasis when no card is hovered. Disposal clears both input references.

Validation: 21 focused opening-focus/fan EditMode checks passed with graphics,
including mounted focus/hover/leave/blur events. No packaged visual acceptance
or full-suite run is claimed. Next scheduled CI check remains .159.

## Reference-proportioned opening controls (0.5.157)

The primary controls now follow the supplied screenshot's proportions at the
1280 x 720 reference viewport: 180 x 40 buttons, a 54-pixel inter-button gap,
and a higher action row beneath the hand rather than at the bottom edge.
Typography, rounded corners, and glow bounds scale with the smaller controls.
This leaves the full glow visible and restores the reference's lower margin.
The values are presentation measurements, not extracted Arena engine constants.

Shared geometry keeps textured buttons, fallback buttons, and glow holders
aligned. Text padding is reduced so the supplied title font fits the shorter
button. Engine callbacks, labels, input guards, and viewer cleanup are unchanged.

Validation: 22 focused EditMode checks passed (opening controls, glows, and
hand geometry), packaged build succeeded, and the live artwork opening action
and cleanup were checked with screenshot inspection. Next CI check: .159.

## Supplied Arena button glow (0.5.156)

The opening controls now layer the supplied `MainButton_Glow` behind the blue
Mulligan and orange Keep button artwork. The tint follows each primary action.
The Image ignores pointer picking; original buttons and callbacks remain intact.
Glow visibility follows enabledInHierarchy each UI tick, so pending submission
does not retain a ready-state halo. Cleanup removes the decoration and restores
the buttons to their parent without retaining card/decision data.

Re-run `python tools/prepare_play_arena_buttons.py` before building. The existing
pinned button bundle also supplies Texture2D path ID 5914490896537385971,
288 x 79. PNG/provenance stay ignored and Downloads remains unchanged.
`--arena-buttons` now verifies both artwork skins and both glow layers.

Validation: 22 focused EditMode checks passed (glow input/state/cleanup,
button mapping, and hand geometry), packaged build succeeded, and the live
artwork opening/engine action/cleanup was checked with screenshot inspection.

Third-commit CI checkpoint: .151, .152, and .153 desktop previews passed; their
general Tests runs were cancelled. .154 desktop preview passed and Tests was
cancelled. .155 Tests/desktop preview were still running at the check and remain
deferred. No completed failure was found. Next scheduled check: .159.

## Arena-style opening header hierarchy (0.5.155)

The engine-owned mulligan prompt now sits beneath the centered Opening Hand
heading, matching the supplied Arena reference's heading/subheading/hand/action
hierarchy. Symmetric side padding and adjusted stage spacing keep the fan below
the header. The bottom area contains the primary Mulligan and Keep controls.

The existing prompt Label is moved after option mapping; its live updates and
clearing remain owned by ViewerDecisionPanel. Disposal explicitly removes the
label even when a layout has reparented it. No turn-order or opponent-keep
statement is inferred. Rules text remains unavailable under the current live
contract rather than being filled from printed text as current rules.

Validation: 20 focused EditMode tests and one mounted PlayMode cleanup regression
passed. Packaged build and the real artwork opening/engine action/cleanup were
checked with screenshot inspection. Next scheduled CI check remains .156.

## Screenshot-matching Arena battlefield (0.5.154)

A broader inspection of the supplied battlefield bundles located the actual
backdrop shown in the user's reference: `SOS_BF_NoInteractables`, including the
green/gold floor, library, and central rail. It replaces the temporary cropped
Strixhaven floor for `--arena-backdrop`. The complete texture fills the viewport,
dimmed behind the opening hand; no gameplay objects, avatars, life totals, or
opponent state are baked into the selected image.

Re-run `python tools/prepare_play_arena_backdrop.py` before building, then launch
`python tools/check_play_unity_live.py --artwork --arena-backdrop --arena-buttons`.
The preparation tool pins source bundle
`Textures_Scene_Battlefield_SOS_227120da-8629b126fc8376c7ceac3a327c604380.mtga`
with SHA-256 `ae4fd8edfddd3ce813e7d65be80d56cf2389e8c42259a9d74b6b4d269f6b0c97`,
Texture2D path ID 2994448792846277816, and dimensions 2048 x 1024. Decoder and
suppressed-version fallback remain pinned. The old local Strixhaven PNG is
preserved; the new PNG/provenance is also ignored. Downloads remains unchanged.
The live check now verifies the reported backdrop resource identity as well as
successful presentation, preventing an old player from silently passing.

Validation: 15 focused EditMode tests passed (full-board viewport, layering,
input isolation, and fan geometry), packaged build succeeded, and the live
artwork opening/engine action/cleanup was checked with screenshot inspection.
Next scheduled CI check remains .156.

## Clean noncreature printing footer (0.5.153)

Raised lands revealed a dark printed-stat mask that the live surface previously
requested for every card. Normal-frame printing metadata now records whether a
stat box may exist. Known noncreature Land/Artifact/Enchantment printings skip
that unnecessary mask, preserving their supplied frame/footer. Creature,
planeswalker, battle, unknown, and other layout profiles retain conservative
masking. The decision uses printing metadata, so a printed creature that becomes
an artifact still hides stale printed stats. Current engine stats remain separate.

Validation: 50 focused EditMode tests passed (CardView rendering and opening
focus, including noncreature/creature/unknown printing masks), packaged build
succeeded, and the artwork opening action/cleanup was checked with focused-card
capture inspection.

Third-commit CI checkpoint: the previously deferred .149 desktop preview passed;
its general Tests run was cancelled. .150 and .151 desktop previews passed;
.150 Tests was cancelled. .151 Tests and .152 Tests/desktop preview were still
running or pending at the check and remain deferred. No completed failure was
found. Next scheduled check: .156.

## Opening card hover and focus (0.5.152)

The Arena-reference opening fan now emphasizes a card on pointer hover or
keyboard focus: it rises slightly, enlarges to 112%, and draws above adjacent
cards. Horizontal correction keeps the enlarged card within the hand viewport.
Leaving or blurring restores its original scale and fan order. This is
Manaforge-owned presentation behavior; the scale is not claimed as an extracted
Arena constant. The supplied fan geometry and button assets remain in use.

No engine inspection/action token is created. Existing diagnostic inspection
remains available. The focus controller unregisters callbacks and drops card
references when the viewer closes; cleared/foreign cards cannot be reattached.
The packaged capture now includes `focused.png` before restoring the ordinary
hand and submitting the existing opening action.

The raised-card screenshot exposed gateway default 0/0 on lands; the surface
now shows power/toughness only for creature type lines, preserving values such
as */*.

Validation: 20 focused EditMode tests passed (focus, stat visibility, and fan),
packaged build succeeded, and the real artwork opening/cleanup was checked.
Next scheduled CI check remains .153.

## Supplied Arena button textures (0.5.151)

The recognized opening controls can now use the actual supplied
`MainButton_Blue_Up` and `MainButton_Orange_Up` textures rather than flat fills.
Prepare them with `python tools/prepare_play_arena_buttons.py`, rebuild, then run
`python tools/check_play_unity_live.py --artwork --arena-backdrop --arena-buttons`.
The last flag requires successful texture presentation. Without local textures,
the existing blue/orange controls remain usable. Button identities, callbacks,
labels, and enabled state are preserved; standard UI disabled treatment remains.

Preparation verifies source bundle SHA-256
`30e808233a4b573403dc44d2ec36b710d56064a4c62e14c3ccbdb39f2052b725`
for `Textures_Bucket_EventComponents.MainButtonComponentPayload_0_054bf470-5417e6ab9a508e652dbd8e6e7864781c.mtga`.
The two 440 x 100 Texture2D path IDs are -5175006699134861056 (blue) and
-8745388354193192827 (orange). UnityPy 1.25.4 uses the explicit suppressed-version
fallback 6000.3.14f1. Decoded PNGs and provenance stay in ignored local resources;
Downloads remains unchanged and differing existing images are preserved.

Validation: 20 focused EditMode tests passed (mapping, texture fallback/state,
and hand geometry), packaged build succeeded, and the artwork opening check
requires both skins before submitting the existing engine action and checking
viewer/process cleanup. Next scheduled CI check: .153.

## Uncluttered opening presentation (0.5.150)

The opening keeps the Arena-reference hand fan, centered heading, and bottom
Mulligan/Keep controls. Connection status, fixture limitations, and all seven
inspection buttons now live in a collapsed `Connection details / inspect`
panel at the upper left. Expanding it preserves the original live labels,
buttons, callbacks, and disabled state. The hand stage reserves space below
the heading; non-opening gameplay diagnostics retain their existing layout.
This follows the supplied MulliganBrowser's separation of the hand and primary
actions from secondary controls, without inventing opponent or turn facts.

Validation: 19 focused EditMode checks passed (details containment, opening
control mapping/fallback, and fan geometry). Packaged player build succeeded;
real artwork opening and engine action/cleanup were checked again.

Third-commit CI checkpoint: .146 deferred Tests and desktop preview both passed;
.147 live Java opening and desktop preview passed; .148 desktop preview passed.
The .147/.148 general Tests runs were cancelled, not successful. At the check,
.149 Tests and desktop preview were still running and were deferred to the next
pass. No completed failure was found. Next scheduled check: .153.

## Arena-style mulligan labels (0.5.149)

The recognized initial seven-card XMage opening now presents blue Mulligan and
orange Keep 7 controls, using the supplied Beleren title font and brighter
outlines. The supplied Arena MulliganBrowser separates Keep/Mulligan actions;
Manaforge retains the actual engine button instances, command callbacks,
option IDs, and enabled state while applying those presentation labels.

Relabeling requires the exact normalized prompt `Mulligan down to 6 cards?`,
a seven-card hand, and exactly two options in the expected Yes/No order.
Other prompts, option orders, hand sizes, or extra actions retain engine text.
No turn order, opponent keep result, or mulligan rule is invented.
The typography helper now accepts UI Toolkit TextElement, including buttons.

Validation: 18 focused EditMode checks passed (control mapping/fallback and fan).
The packaged live opening check also requires successful control mapping and
submits the existing Mulligan callback before checking viewer/process cleanup.
Next scheduled CI check remains .150.

## Supplied Arena floor backdrop (0.5.148)

The artwork opening can now show the supplied Strixhaven floor behind the hand.
Prepare it with `python tools/prepare_play_arena_backdrop.py`, build the player,
then run `python tools/check_play_unity_live.py --artwork --arena-backdrop`.
Add `--interactive` for manual input. The default launch remains unchanged.

Preparation uses the existing isolated UnityPy 1.25.4 environment and verifies
bundle SHA-256 `6b0bb5f72c0e34639946c1d3f294c6431f16c4be50e381da64014efbc44e82f4`
before decoding `tex_floor_d` (Texture2D path ID -8961145794100977760,
2048 x 1024) from the supplied STX texture bundle. The suppressed Unity version
uses the explicit 6000.3.14f1 parsing fallback. Local PNG/provenance/resources
remain ignored; Downloads is unchanged. Existing differing PNGs are preserved.

Unity displays a dimmed, cropped central floor region behind all controls,
with pointer picking disabled. This is a flat backdrop preview, not the complete
Arena battlefield: no environment geometry, shaders, avatars, or invented game
state. Arena's supplied static layout separates local/opponent regions; those
regions still need integration with live state.

Validation: 15 focused EditMode tests passed (backdrop layering/input/fallback
and opening fan), packaged build succeeded, and the real Unity -> Java -> XMage
opening passed with seven artwork cards, a displayed backdrop, an engine choice,
zero retained artwork on close, and process cleanup. Capture inspected under
`Artifacts/UnityLive-35ed247d06/connected.png`. Next scheduled CI check: .150.

## Real artwork in the Arena-reference opening (0.5.147)

The live fixtures now preserve actual catalog printing/Oracle IDs rather than
synthetic printing placeholders. The artwork-only opening uses explicitly chosen
modern standard-frame M21/272 Forest and M15/223 Ornithopter decks. The original
M10/SOM Forest/Memnite gameplay probes remain unchanged. Their 2003 frames are
deliberately outside the existing component-renderer compatibility guard; no guard
was relaxed and no selected printing is silently replaced.
Run `python tools/check_play_unity_live.py --artwork --interactive` to prepare a
viewer-scoped bundle from the existing Core cache and launch the fanned opening.
Both exact images must already be cached; the launcher explicitly forbids network
fetching and never substitutes another printing. The two public development
images were cached once through the existing Core service, not a new downloader.

Unity reuses the existing verified CoreArtworkBundle/ViewerSessionHost pipeline.
It waits for artwork for permitted, identified cards before reporting ready and
checks artwork bindings are cleared after the viewer closes. The hand fan refreshes
when asynchronous artwork arrives, so binding does not leave cards unrotated.
Source-only/no-artwork launches retain their unavailable-art behavior. No image
binaries, Downloads assets or card/deck database formats are added to Git.

The supplied Arena reference still defines the visual target. This step fills the
existing card-renderer artwork slots; it does not complete Arena frame materials,
battlefield assets, avatars, mulligan semantics or continuous gameplay. Existing
authoritative text/identity and privacy boundaries remain unchanged.

Local focused validation passed: 12 graphics-enabled artwork host/surface tests
without skips, 28 Python bundle/bootstrap tests, the final player build and the
packaged art opening with all seven hand bindings loaded and zero after clearing.
Screenshot review confirmed real art in the fan; diagnostic notices were moved
to the header to avoid collector-footer collisions. The no-artwork opening and
the original native Memnite cast/metadata/resolution regression also passed. All
owned roots exited normally. Lint and formatting pass; no full application suite
ran. Existing Unity asset/settings edits were preserved. The .147 CI check found
.145 live/protocol/preview success; .146
preview and general Tests were still running and deferred. Prior general Tests
were cancelled; no new completed failures were found. Next CI review is .150.

## Arena-reference opening-hand composition (0.5.146)

The owner reaffirmed MTG Arena as the visual target, with the supplied Downloads
assets/reference implementation as the source. Read-only inspection of Core.dll's
MulliganBrowser and CardLayout_Fan confirmed separate header/subheader/consequence
regions, engine-driven button models, desktop hover support and a centered fan
with a 4-degree maximum step and 30-degree total-angle cap. Local decompiled
inspection files remain ignored under Artifacts/ReferenceVisuals; source Downloads
are unchanged and no supplied implementation or bundle is committed.
The inspected Core.dll SHA-256 is
`48347a833961d311da7a3ccdecc6116f3ee75b6db8fa313b1871aecea8b54e85`.

The packaged live opening now uses a Manaforge-owned screen-fitting fan with
large full cards, a dimmed hand surface and centered blue/orange decision controls
below the hand. Existing CardView/typography, inspection and authenticated choice
callbacks are reused. Geometry adapts to width/count, updates only after layout/
revision changes and retains no private card references or new gameplay callbacks.
Land, priority and casting-ability fixture layouts remain unchanged.
Known engine font tags are removed from the opening question for plain display;
line breaks, wording, unknown tags and symbol tokens are preserved.

This implements the opening composition, not the full Arena presentation. Actual
battlefield assets, avatars, polished animation and artwork wiring remain open.
Engine option labels remain authoritative Yes/No until explicit mulligan semantics
are available; no Keep N, opponent-keep status or return counts are invented.
The existing single-decision clear/close behavior is preserved.

Thirteen focused Unity EditMode geometry/text checks passed across multiple hand
counts and widths, including bounds, ordering, symmetry, invalid input and prompt
formatting. The initial packaged opening and unchanged priority-pass regression
passed. The final Windows player build and packaged opening proof passed as well;
capture review confirmed the full fan, readable plain question and visible bottom
controls. All owned roots exited normally. The owner's five pre-existing Unity
asset/settings edits were backed up and restored after editor/build checks.
No full application suite ran; artwork and complete Arena visual acceptance remain
open. Next CI review remains .147.

## Native source-incarnation and selected-ability observation (0.5.145)

The guarded metadata reader now returns a stack spell's physical source counter
and native spell-ability IDs only for requested, identified spell objects. The
Java proof reads the source's owner/counter in the original hand frame before
native submission, freezes that observation, and requires a later source-counter
increase plus the exact single selected ability on the stack. Missing, unchanged,
stale, malformed or ambiguous observations cannot satisfy this check.

The opt-in metadata proof adds `native_cast_instance_matched`. It also requests
the stack object without identified-object permission and requires both detailed
fields to be absent. Detailed IDs/counters remain private Java metadata; the
public snapshot, Unity and sanitized report gain no native identity fields.

This demonstrates an observed engine incarnation transition and ability match in
the fixed Memnite scenario. It does not prove arbitrary cast outcomes or choose
a receipt policy. No confirmed receipts, pending-ledger changes, automatic mana
or additional Unity commands were added. Continuous outcome reconciliation is
still open.

Local focused Java protocol checks passed, including 211 projection/privacy/
observation checks and 28 metadata transport checks. The real-engine instance/
ability match, unidentified-object redaction and cast/resolution probe passed with
normal owned-root cleanup. All 75 focused Python adapter checks, lint and
formatting passed. No full application suite or Unity build ran. Next scheduled
CI review remains .147.

## Direct Java guarded stack-source metadata (0.5.144)

`python tools/check_play_live_opening.py --first-creature --native-metadata
--output Mtg_Projects/mtg_play_unity/Artifacts/FirstCreature/report.json` (one
command line) now proves the exact native stack-to-source link through the
existing guarded metadata reader. The client validates the same game/viewer/
cycle, source-card absence from hand, stack visibility and native owner/controller
mapping. The sanitized report adds `native_stack_source_matched`; no native IDs
or metadata payloads enter the uploaded report.

Python provisions the channel once during startup: it supplies a fresh key over
private owned pipes, receives the Java-owned match's game/viewer in a transient
private workspace marker, starts a game/viewer-bound listener through the server
control pipe, and privately supplies its loopback address to Java. Startup files
are consumed and deleted; keys never enter disk or argv. All subsequent metadata
queries run directly Java-to-Java, not through Python or response files. Initial
bootstrap reads rely on the owning parent's startup deadline/EOF; normal lifeline
monitoring starts after that private exchange.

ManaforgeServerHost starts no listener by default, permits only one provisioned
channel, reuses ManaforgeGameMetadata's native response-monitor/cycle/visibility
checks and closes the channel during shutdown. The Java client reuses existing
authentication/framing, validates bound requests, clears its handshake key copy
and closes on uncertain transport failure without replay. The shared native
compiler source list now explicitly includes the channel and protocol dependencies;
no payment policy or installed engine artifacts changed.

This is source-correlation evidence, not receipt confirmation: source-incarnation
and exact ability/outcome reconciliation still remain. Existing pending ledger
guards are unchanged. Unity's ability fixture continues using its existing route;
the metadata channel is currently opt-in for the Java-owned proof only.

The .144 CI check found .142 live/protocol/preview and .143 protocol/preview
success. .143 live-opening and general Tests were still running and deferred;
prior general Tests were cancelled. No new completed failures were found. Next
scheduled CI review is .147. Local validation passed: the real source-metadata/
cast/resolution proof, 194 projection checks, 28 private transport checks, existing
Java protocol/socket checks, 147 pinned native object checks and shared bridge
compilation, plus the packaged Unity ability regression. Lint and formatting
checks pass. No full application suite or new Unity build ran.

## Private metadata transport foundation (0.5.143)

ManaforgeMetadataChannel provides an isolated Java listener with the existing
loopback framing and fresh challenge/proof authentication. One configured game/
viewer is bound before listening; only six-field read-only metadata requests are
accepted. Object lists are bounded, unique canonical UUIDs; identified objects
must be a subset of requested objects. Cross-game/viewer requests, mutations,
paths, duplicate JSON keys and malformed cycles fail closed before the reader.

The listener accepts one authenticated owner, limits frame/auth/read/write waits
and total requests, clears its private key copy and owns its socket/worker cleanup.
The injected reader receives only a validated copy. Native errors become a fixed
private error code rather than exception details. Close interrupts the worker and
reports uncertain cleanup if a reader does not return within the join bound; it
does not claim to forcibly cancel arbitrary native work.

This foundation is deliberately unmounted: ManaforgeServerHost, Unity and the live
gateway do not start it, and no real metadata is read yet. It grants no new root/
all-seat Unity access, confirms no gameplay receipt and adds no Python per-action
relay. Private runtime bootstrap/client ownership and binding to the existing
guarded native reader remain next. Local focused validation passed: 26 bounded
request/authentication/privacy/lifecycle checks, including a deliberately blocked
reader that must report uncertain cleanup; all 185 projection checks and the
existing Java protocol/socket suite. Lint and formatting pass. No real-engine
metadata, full application suite or Unity build ran. No UI or payment policy
changed. Next scheduled CI review remains .144.

## Native card-to-ability correlation evidence (0.5.142)

The private bridge view now retains XMage's basic casting-ability IDs by native
source object. An immutable read-only NativeCastCorrelation observation captures
the actual submitted cast source, offered IDs and native game/viewer/decision/
cycle, then checks the next single ability choice against those IDs. Invalid,
duplicate or missing IDs, changed viewers/games, stale decisions, mismatched
cycles and concealed/missing sources fail closed. The raw IDs never enter the
Unity snapshot; the sanitized proof adds only `native_cast_ability_matched`.

The real Memnite fixture now requires this match before submitting its ability
choice, in both Java-only and packaged Unity modes. It remains observation
evidence, not permission to act, proof of a complete cast, or a confirmed receipt.
The existing native decision gate remains authoritative. No receipt ledger or
pending-command behavior changed.

Pinned API inspection found that Spell.getId identifies the stack object while
Spell.getSourceId identifies its physical card. The client CardView parent-ID
fallback does not establish that relationship. The existing guarded server
metadata already exposes stack sources, but Java does not yet own its delivery
channel. That channel plus incarnation/outcome correlation is still needed before
settling casting receipts or admitting continuous Unity commands. No unsupported
identity relationship is inferred from matching names, counts or advancement.

Local Java protocol preflight passed with 185 projection/privacy/observation
checks. The real Java cast/ability/resolution probe passed with the exact offered
ability match and normal owned-root cleanup. The packaged casting-ability
regression also passed, as did all 75 focused Python adapter checks. Lint and
formatting checks pass. No full application suite or new Unity build ran; no
Unity C# or payment policy changed. Next CI review remains .144.

## Packaged native casting-ability choice (0.5.141)

The opt-in `python tools/check_play_unity_live.py --creature-ability --interactive`
scenario mounts the real XMage casting-ability choice in Unity's existing decision
panel. Diagnostic pregame/keep, priority passes and the card-source click occur
before Unity connects. Select the offered ability within 60 seconds; Java checks
native acceptance, hand decrease and the Memnite stack entry, then Unity clears
and closes. This is one explicit ability choice, not continuous casting UX.

The original submission remains conservatively uncertain; no next Unity command
is admitted on the basis of advancement alone. The packaged report explicitly
leaves `creature_resolved=false` and records `unity_casting_ability_submitted` and
`creature_spell_on_stack`. Resolution continues to be proven separately by the
Java-only `--first-creature` scenario. No nested diagnostic priority passes follow
the Unity submission, and no pending-ledger protection was relaxed. Full receipt
reconciliation remains necessary for a continuous authenticated client session.

The existing private bootstrap, authenticated session, renderer and decision
panel are reused. No post-land display, stack UI or mana policy was added. The
new flag is mutually exclusive with land/pass scenarios; the opening route is
unchanged. A real-socket ability-choice check requires duplicate receipt reuse
and exactly one native submission.

The .141 CI review found .138 protocol/preview/live-opening and .139 protocol/
preview success. .139 live-opening and .140 Tests/protocol/preview/live-opening
were still running and deferred; general Tests for .137-.139 were cancelled.
No new completed failures were found. No full-suite success is inferred from
cancelled runs. Next scheduled CI review is .144.

Local validation passed: current Windows player build, 158 projection checks and
the focused Java protocol/socket suite, packaged ability submission with native
stack evidence and clearing, packaged priority-pass regression, and the separate
real Java creature-resolution proof. All owned roots exited normally. Screenshot
review confirmed the casting button; fallback artwork and raw engine markup in
the prompt remain known presentation limitations. Lint/format checks pass. No full
application suite ran and no continuous-session acceptance is claimed.

## Native creature resolution through explicit priority (0.5.140)

The Java-only `--first-creature` fixture now continues after its observed Memnite
stack entry. An explicit diagnostic pass uses the authenticated session boundary
and current native priority token. Acceptance additionally requires stack
clearance, the expected reduced hand count and exactly one visible 1/1 Memnite
on the human battlefield. The additive `creature_resolved` report field records
this fixed public scenario, not a general reconciliation or complete-game result.

A dedicated pass-only projection permits a nonempty native stack while explicitly
listing `stack` as unsupported. It never serializes stack contents or reconstructs
their identities, owners or abilities. It offers only the current human priority
pass, with `actions_complete=false`; cast/land offers remain unavailable in this
mode. Default projections still reject nonempty stacks. Full stack translation,
continuous Unity interaction and production lifecycle/parity remain open. No new
state-display or mana-payment work was included.

The native fixture policy is explicit passing, not installed automatic play. Every
pass retains existing revision/decision/viewer binding, one-shot native claiming,
duplicate receipt handling and conservative disconnect uncertainty. Local Java
protocol preflight passed, including 158 projection/privacy/token checks. The real
cast/ability/priority/resolution scenario passed with normal owned-root cleanup;
lint and formatting checks pass. No full application suite or Unity build ran.
Existing live CI includes the strengthened scenario. Next scheduled CI review
remains .141.

## Engine-offered creature casting port (0.5.139)

An opt-in live projection now includes `cast_spell` actions from the pinned
engine's playable hand objects. It preserves selected printing bindings, opaque
source/action tokens, current human priority and the existing one-shot claim and
receipt path. It does not calculate costs, card legality or targets. Default
opening/land/priority projections do not enable spell offers.

The new Java-owned public fixture uses a 60-Memnite human deck and a 60-Forest AI
deck. Diagnostic pregame/keep and pre-cast priority passing remain explicit
fixture policies. Run `python tools/check_play_live_opening.py --first-creature
--output Mtg_Projects/mtg_play_unity/Artifacts/FirstCreature/report.json` on one
command line. An authenticated client submits an actual engine-offered cast;
the diagnostic checks hand count decrease and a Memnite stack entry. Duplicate
commands reuse their receipt rather than executing again. The report's
`creature_spell_on_stack` does not imply resolution or a confirmed command result.

XMage requests a distinct ability choice after the source click. The opt-in
projection now maps bounded native ability choices to opaque public option IDs;
the same claim guard translates the selected option back only at native submission.
Malformed IDs, labels and oversized/empty offers fail closed. The diagnostic
answers only a single engine-offered ability; ambiguous/multiple abilities stop
the fixture. This choice remains separate from the preceding cast submission.

No nonempty stack is projected to Unity yet, and no Unity casting controls,
mana/payment policy or post-land state display were added. The existing live CI
workflow now runs this additional native scenario and uploads only its sanitized
report. Local validation passed: 142 projection/privacy/token checks and the
focused Java protocol preflight; real-engine cast, native ability selection,
hand decrease and Memnite stack observation; duplicate receipts and normal owned
shutdown. The real land/pass regression also passed. Lint and formatting pass.
No full application suite or Unity build ran. Next scheduled CI review remains .141.

## Packaged explicit priority pass (0.5.138)

Run `python tools/check_play_unity_live.py --priority-pass --interactive` to
review one real human priority pass in the packaged Unity client. Diagnostic
pregame/keep and one Java-peer pass precede this offered window. Click Pass
priority within 60 seconds. Java submits the exact bound native boolean false,
observes engine advancement, then sends conservative uncertainty; Unity clears
the viewer and closes. This is a one-action integration fixture, not continuous
play, a completed turn, or the requested finished battlefield presentation.

The existing decision panel and authenticated session are reused. This scenario
shows only the pass control; `--first-land` retains land-only controls. The two
scenario flags are mutually exclusive. Reports distinguish actual native land
observation from an explicit Unity priority submission, so a pass cannot satisfy
the land check. A real-socket regression checks duplicate receipt reuse with only
one native pass submission. No post-land display work was included.

The .138 scheduled CI check found successful .135 protocol, preview, live-opening
and native-payment jobs and successful .136 preview/live-opening jobs. The general
Tests runs for .135/.136 were cancelled, so they provide no full-suite result.
The .137 Tests/protocol/preview/live-opening jobs were still running and deferred
to the next pass; prior inventory/lint/format failures were already repaired at
.135. No new completed failures were found. Next scheduled CI review is .141.
Local focused Java protocol checks passed, including the new authenticated socket
pass/duplicate test and 110 projection checks. Both packaged priority-pass and
first-land scenarios passed with normal root cleanup. The pass report explicitly
records `unity_priority_pass_submitted=true` and `first_land_observed=false`.
Screenshot inspection confirmed a single visible Pass priority control. The final
player refresh corrected a stale land-only descriptive note; its packaged pass
scenario also passed. The original packaged opening regression passed as well.
Lint and formatting checks pass. No full application suite ran.

## Authenticated native priority passing (0.5.137)

An opt-in projection now exposes the current human priority window as an opaque
`pass` action, bound to the same game/viewer/decision/cycle as land actions. Its
one-shot native response is boolean false, matching the reference adapter and
bridge. Nonpriority prompts and default projections do not gain pass actions.
Synthetic checks cover replay, stale offers, mismatched tokens and pass-only
windows. No rules or strategic passing policy are implemented by Unity.

The public all-Forest first-land diagnostic now submits at least one explicit
pass through the authenticated session boundary before playing a land; pre-land
windows use that boundary as well. It checks native transport acceptance and
subsequent engine advancement, separately from receipt confirmation. The report
adds `priority_pass_submitted`; neither this nor advancement proves a completed
turn or match. This is an explicit fixture policy, not product auto-pass.

The single-land Unity fixture retains land-only controls and its existing clear/
close behavior. It does not expose a pass button whose outcome its single-land
completion check cannot handle. The owner declined the proposed post-land display
increment; that work is deferred. Continuous public priority controls remain next.
Local Java protocol preflight passed, including 110 projection/privacy/token
checks. The real-engine Java pass-to-land probe passed with duplicate receipt
reuse, one native submission per command, engine advancement and clean shutdown.
The packaged first-land regression also passed with explicit native pass evidence,
authenticated land input, viewer clearing and normal root cleanup. No Unity C#
changed or new player build was needed; no full application suite ran. Next
scheduled CI review remains .138.

## Packaged first-land controls (0.5.136)

The opt-in all-Forest fixture can mount a real land offer in Unity's existing
ViewerDecisionPanel. Run `python tools/check_play_unity_live.py --first-land
--interactive` from the repository root (both flags on the same command line).
Choose an offered Play land action within 60 seconds. This is an integration
review, not the requested finished battlefield/mulligan presentation. The diagnostic performs
pregame choices, keeps the opening and passes pre-land priority windows in Java;
these fixture policies are not installed gameplay automation. The default opening
review command continues to offer its original boolean decision.

The mounted button submits its opaque engine-bound action through the existing
authenticated session/receipt path. Java checks native acceptance and observes one
fewer hand card and one additional human battlefield object before emitting the
conservative uncertain receipt. No confirmed outcome is fabricated. Unity clears
the viewer and closes after this single action; it does not yet render the new
battlefield or provide a continuous mulligan-to-land match. Artwork and the owner's
requested Arena-style presentation remain pending.

The scripted form, `python tools/check_play_unity_live.py --first-land`, invokes
the actual mounted action button and requires native first-land evidence in
addition to existing authentication, viewer clearing and root cleanup checks.
Local packaged first-land validation passed: current Windows player build, actual
mounted action input, authenticated Java admission, native land zone change,
viewer clearing and normal owned-root cleanup. Screenshot inspection confirmed
visible controls with fallback cards; it does not establish visual acceptance.
The focused Java protocol preflight also passed, including 93 projection checks.
The default packaged opening regression also passed with native advancement,
viewer clearing and normal root cleanup. No full application suite ran. Next
scheduled CI review remains .138.

## Live land priority binding and CI repair (0.5.135)

Land projection now requires the native priority player to resolve to the human
viewer. Unknown, absent or opponent priority fails closed and invalidates the old
offer. Added action-token regressions cover session/viewer/revision/decision/action
mismatches, retry after rejection, replaced offers and face-down source exclusion.
All 93 projection checks and the focused Java protocol preflight passed. The real
XMage first-land probe also passed with the stricter priority requirement, engine
advancement and clean owned-root shutdown. Unity land controls remain pending.

The scheduled CI review found successful .133 protocol, live-opening and desktop
preview jobs. The .134 general Tests jobs failed before application tests because
the Python source inventory omitted existing diagnostic labels, one preview import
was unused, and eight Play files needed formatting. Regenerated inventory changes
only diagnostic string candidates, not wire records or commands; removed the import
and applied the existing formatter without gameplay changes. No unfinished runs
were present. Local lint, formatting and inventory checks pass; remote verification
of these repairs remains pending. Formatting also required regenerating two
fixture provenance hashes; fixture cases and schema are unchanged. All 191 focused
Python adapter/navigation/preview/connection/artwork/schema checks passed (the
schema checks were rerun after refreshing those hashes). Next scheduled CI review
is .138.

## Owner review and visual direction (0.5.134)

The owner reviewed the packaged opening and found its presentation underwhelming.
Review has occurred; visual acceptance has not. Continue the live integration
roadmap with the owner's supplied Arena screenshots as the presentation target.

- Mulligan: dim the battlefield behind a large, readable, centered fanned hand;
  show who goes first, engine-known opponent keep status, a View Battlefield
  control, and prominent Mulligan / Keep N buttons below the cards. Show return
  counts only when supplied by authoritative decision state; do not hardcode the
  screenshot's seven cards or its mulligan rule.
- Battlefield: opposing seats at top/bottom, centered avatar/life displays,
  opponent card backs above, local fanned hand at the bottom, deck piles at the
  sides, and turn/priority controls at lower right. Preserve room for the play
  surface and later multiplayer layouts. Highlight only engine-offered actions.
- Reference material is in the owner's Downloads. The local `Unity Asset Catalog`
  indexes `Assets from Wizards, given with permission`, including battlefield,
  avatar, UI prefab and card-component bundles. These are compiled runtime assets,
  not an editable Unity source project; inspect relevant contents before choosing
  assets. The screenshots supplied in the review define the intended composition.

The existing .133 backend first-land probe passed locally: authenticated public
action admission, one native land submission, hand/battlefield count advancement,
duplicate receipt reuse, uncertainty retention and owned-root cleanup. The focused
Java protocol checks also passed, including 76 opening-projection checks. This
does not establish Unity land controls, polished mulligans or full-game acceptance.
Next scheduled CI review remains .135; leave unfinished runs to the next pass.

Owner priority: move into live integration while retaining the fallback. Formal
G0/G1 acceptance remains open; this direction does not certify those gates.
Start with human versus XMage AI, keeping seat count independent of controller
and future multiplayer layouts. Automatic mana work remains parked.

## First real Java-owned opening (0.5.128)

ManaforgeLiveOpening now creates an actual pinned-XMage freeform match through
the existing ManaforgeBridge in the same Java process. A bounded internal event
sink replaces JSON/stdout round trips for this diagnostic only. The default
bridge CLI is preserved; its connect/status/shutdown path is also exercised.
No engine source fork, rules reimplementation or Python gameplay session is used.

The public fixture contains 30 M10/248 Forest and 30 SOM/174 Memnite for each of
two seats, one human and one engine_ai. Java connects, checks the engine version,
creates the table, joins the AI through XMage's table-owner API, joins the human,
and starts the match. The diagnostic chooses only engine-offered pregame options
and player target IDs, stops at a real seven-card hand plus pending decision,
then disconnects. Its tiny pregame policy is diagnostic code, not product passing
or strategic automation. Unknown prompts fail; it never auto-plays a normal game.
The queue, pregame response count and wall-clock runtime are bounded. Parent EOF
requests cancellation and the parent retains the subprocess handle for timeout
cleanup. This is direct-root ownership, not production OS containment.

Run from the repository root:

```powershell
python tools/check_play_live_opening.py
```

Use --xmage-root and --jdk-path for alternate installed paths. Hash validation,
workspace preparation, compile and server lifecycle reuse connection_proof.
Python coordinates the isolated server and diagnostic processes; all match
creation and pregame response commands execute in Java. An existing idle proof
client performs only connection/status checks, not match actions.

The local focused live proof passed after correcting the diagnostic username
length and adding the engine's pregame player-target decision. It confirmed an
actual opening hand and pending decision, then normal cleanup of the diagnostic,
reference client and XMage server. No full application suite ran. Dedicated
Play live Java opening CI prepares the hash-pinned runtime and runs the same
proof, uploading only Artifacts/LiveOpening/report.json. CI is next checked at
.129; no CI success is claimed for this increment yet.

The report contains fixed evidence booleans, opening-hand count and source commit,
without cards, engine UUIDs, player names or prompt contents. Runtime bridge logs
remain local diagnostics for this public fixture and are not uploaded. Never use
this harness as a user-deck exporter or send its raw engine callback JSON to Unity.

## Remaining live vertical slice

1. Translate the live human view and outstanding decision into the existing
   viewer-filtered public snapshot/choice contracts. Preserve opaque incarnations,
   exact identities, decision/revision binding and unknown/unsupported fields.
2. Route explicit Unity choices through the authenticated Java session boundary
   to the current XMage decision. Python must stay outside per-action exchange.
3. Mount that live source in the existing Unity session scene, then stop for owner
   UI verification of the real opening hand, keep/mulligan and priority controls.
4. Extend to land, creature, mana, stack, combat and a natural authoritative result.
   Compare meaningful behavior against the existing Python adapter as reference.
5. Integrate saved-deck launch manifests, complete readiness/descendant cleanup,
   privacy acceptance and packaged lifecycle before enabling installed Play.

Unity is not connected by this first increment. No full match, public protocol
parity, AI UX, hidden-information boundary or live Unity gameplay is claimed.
Existing fixture UI reviews remain pending; this increment changes no Unity UI.


## Opening public projection (0.5.129)

ManaforgeOpeningProjection now converts the real human opening view and its
GAME_ASK decision to the generated PlayContracts DTO model. The live Java proof
validates its resulting envelope with the same ReceiveMessages/schema used by
the Unity channel, in non-synthetic protocol mode. The diagnostic still reports
public_fixture_only because its decks are public fixtures; it does not relabel a
live engine state as a fake engine snapshot.

This read-only opening scope requires the bound engine viewer, matching state/
decision cycle, a numeric engine decision ID, empty board/stack/exile/combat and
an engine boolean decision. Unsupported states fail with a fixed error. It does
not omit a live occupied zone and pretend the rest is complete. Player seats are
mapped without a fixed maximum. Opponents expose counts/public life only; the
projection reads only the bound local hand. Concealed/face-down cards have no
characteristics or printing identities. Engine IDs/names and unknown raw fields
are not copied. UUIDs inside permitted display text are redacted.

Selected-printing bindings come from trusted host mappings by set/collector pair;
there is no name fallback or invented printing. Unknown bindings remain null.
The public fixture supplies its existing selected-forest/selected-memnite IDs.
Metadata requiring the server's full physical-incarnation information remains
unfinished. Object/choice IDs are fresh per projection, with incarnation support
explicitly unavailable; this opening-only helper must not be used for animated
live board transitions. It returns fresh DTO JSON without retaining caller-mutated
output or shared binding objects. actions_complete is false, actions are empty,
and unavailable characteristics and session fields are marked unsupported.

Boolean options reflect the engine's yes/no prompt, with fresh public tokens.
No Unity command endpoint or token-to-native submission map is connected yet;
these tokens must not be accepted by an executable gateway until that mapping
and current revision/decision validation are implemented. No raw engine view
is sent to Unity or persisted as a snapshot artifact.

Validation passed: 30 isolated Java checks (shared receive shape, concealed/
face-down cards, opponent canaries, raw IDs, unknown printing, source/output
isolation, mismatched viewer/cycle, occupied zones, malformed numbers and
unsupported decisions); the Java protocol preflight; 28 focused process-runtime
checks; and the actual human/AI opening with its public snapshot schema check
and normal cleanup. No full application suite or Unity UI ran. CI now includes
the projection checks and reruns the live proof for protocol-runtime changes.

Scheduled CI check: [.127 protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41257622899),
[.127 preview](https://github.com/RyMeep128/Manaforge/actions/runs/41257622905) and
[.126 dependency fix](https://github.com/RyMeep128/Manaforge/actions/runs/41257263652)
passed. [.128 live opening](https://github.com/RyMeep128/Manaforge/actions/runs/41260532957)
and [.128 preview](https://github.com/RyMeep128/Manaforge/actions/runs/41260532996)
were still running and were deferred. Check the next increment at .132 without
waiting on unfinished work. No G0/G1 gate or full gameplay acceptance is implied.

Next: bind the engine boolean decision to authenticated public choice submission,
then mount the live source in Unity and request owner UI verification.


## One-shot opening choice binding (0.5.130)

The opening projection now retains a private mapping from its two public option
IDs to the native boolean decision. claimBoolean parses the existing command
schema and reuses WireMessages.checkBinding. It checks trusted host session/
viewer context, public revision/decision/option, engine viewer/game/decision and
cycle before producing a private respond command for the existing bridge.

The claim is synchronized and consumed before native IO, so two simultaneous
submissions or a retry after uncertain IO cannot create a second native command.
Rejected bad bindings do not consume a valid choice. Reprojection invalidates old
tokens before validation, including when the new state is unsupported; explicit
invalidation supports disconnect/shutdown. Public DTO/output mutation cannot
change the retained token/value mapping. Native IDs remain in the trusted adapter
only, never in the public snapshot.

The host-context arguments are trusted internal inputs, not authentication. This
helper must be called by the future authenticated session worker using its verified
viewer context and current engine state, never using caller-supplied identity or
current-state assertions. The existing GatewaySessionBoundary and submission ledger
still need wiring around enqueue, receipt/uncertainty handling and this native claim.
This increment creates no network listener or unauthenticated command endpoint.

The public diagnostic now chooses Yes through a complete public command envelope,
claims the corresponding native boolean, submits it to XMage, checks accepted
transport submission, rejects replay, and observes a newer engine decision/state.
The fixture's explicit answer is not product automation. Engine advancement is
recorded separately from transport acceptance; it is not a claim that every outcome
or complete match has been confirmed. The existing bridge checks game/decision
again immediately before native IO. Python performs no gameplay actions.

Local validation passed: 63 projection/privacy/binding checks, including both
boolean values, incorrect sessions/viewers/options/revisions/decisions, changed
native game/viewer/decision/cycle, reprojection, invalidation and simultaneous claims;
the Java protocol preflight (60 checks before the final concurrent/native-viewer
cases were added, with all 63 then rerun in isolation); and the real public-choice
submission/replay rejection/engine-advancement scenario with clean root shutdown.
No full application suite or Unity UI ran. CI remains scheduled for .132; no new
CI success is claimed. Owner visual review is not needed for this Java-only change.

Next: compose this binding with authenticated Java session admission and receipts,
then connect the live source to Unity's existing session/decision scene and stop
for owner UI verification. Manual engine actions, board/stack/combat normalization,
full parity, saved-deck runtime resolution and natural game completion remain open.


## Authenticated live opening admission (0.5.131)

ManaforgeOpeningSession composes the verified GatewayHandshake.ViewerContext,
existing GatewaySessionBoundary/SubmissionLedger, opening projection and a bounded
one-command native queue. Admission observes the public snapshot, reserves a
receipt, and claims/enqueues the matching private native response. Socket writes,
engine IO and waits occur only after admission returns, on the serialized owner
worker. It never calls back into the session boundary from its enqueue callback.
Native polling is owner-only; no raw command enters a client channel.

The public diagnostic ManaforgeOpeningLoopback now supplies a real Java client
on authenticated localhost sockets. Fresh viewer keys and client/server nonces
stay in memory. Existing challenge/proof verification precedes ViewerContext
creation, snapshot delivery and choice admission. The client validates the shared
receive shape, submits an explicit Yes command, gets submitted, retries that same
command ID and gets the cached receipt. Only one private native command is polled
and sent to XMage. Engine advancement remains a separate observation.

No confirmed receipt is fabricated. Because exact semantic reconciliation of this
opening answer is unfinished, disconnect leaves its unresolved receipt uncertain.
The diagnostic checks that state before final disposal. Disconnect/cancellation
invalidates choice tokens and clears queued work; socket/worker ownership and key
clearing are handled even on failure. This is serialized-worker coordination,
not production thread joining, persistence or XMage descendant containment.

The loopback client is a public fixture tool, not a production listener, launch
credential API or Unity UI. It does not authenticate an arbitrary external client
or accept user decks. The live adapter session worker is reusable; the next step
is replacing the diagnostic client with the existing Unity authenticated channel.
No public interface or installed Play feature has been enabled.

Local validation passed: the actual XMage authenticated opening choice, duplicate
receipt/one native submission, subsequent engine advancement and normal cleanup;
full focused Java protocol preflight including all 63 projection/binding checks;
and new engine-free real-socket tests for authenticated delivery, cached receipts,
disconnect uncertainty and cancellation before native submission. Cleanup-only
changes were recompiled and those socket tests passed again in isolation. No
full application suite or Unity build/UI ran. CI next check remains .132.

Sanitized live report version 2 adds authenticated_choice, duplicate_receipt_reused
and disconnect_uncertainty_retained. duplicate_native_submission_prevented replaces
the earlier choice_replay_rejected label: retrying the same command returns its
stored receipt rather than a rejection, while still preventing duplicate execution.
No credentials, native IDs, cards or prompts are included in uploaded evidence.

Next: attach Unity's existing session scene and decision panel to this live
opening source, then stop for owner visual/interaction review. Broader actions,
board translation, saved-deck resolution and natural match completion remain open.


## Packaged Unity live opening — owner review required (0.5.132)

The opt-in LiveOpeningScene now uses the existing ViewerSessionHost with
fixtureMode=false, ViewerCardSurface/CardView inspection and ViewerDecisionPanel.
A new -manaforgeLiveOpening route leaves default Play/preview/fixture routes intact.
No new renderer or deck model was introduced. All parsing/networking remains on
existing workers; scene code ticks presentation and counts sanitized evidence.

Run the packaged public-deck slice from the repository root:

```powershell
python tools/check_play_unity_live.py --interactive
```

Allow roughly a minute for pinned-engine validation, compilation and startup.
The player opens without Unity Editor. Inspect the seven-card human opening with
the Inspect buttons and read the engine's mulligan question. Choose Yes or No
within 60 seconds. After submission, the viewer clears and the spike closes.
Yes is an actual engine response, not a simulated UI response; No can keep the
opening hand where that is the offered mulligan question. This is not a playable
full match: land/spell/stack/combat and later decisions remain disconnected.

The headless form `python tools/check_play_unity_live.py` drives the actual mounted
Yes button for public-fixture acceptance and captures connected.png/choice.png
under a fresh Unity Artifacts/UnityLive-* directory. The local packaged proof passed:
real seven-card snapshot, challenge/proof authentication, native response, engine
advancement, submitted then uncertain receipts, renderer clearing and normal owned
root cleanup. The existing synthetic packaged decision fixture also passed against
the same new build. No full application suite ran. The player build succeeded.

Do not interpret uncertain as a confirmed result: advancement is not yet mapped
to full semantic reconciliation. The new live endpoint does not fabricate confirmed
or game-result packets. Scene cancellation clears stale opening cards at the end
of the supported slice. The renderer currently has no artwork bundle for this
fixture. Known review limitations include fallback art, raw engine font markup in
the question and default land P/T display; these are not polished UX acceptance.
The owner must review actual interaction before further UI work proceeds.

The gateway's diagnostic Unity mode receives a fresh viewer key in one private
bounded stdin frame, before its EOF lifeline starts. Only a nonsecret loopback
address marker is written to disk. Unity receives its bootstrap privately through
its separately owned stdin. No viewer keys, manifests or native IDs enter argv,
public reports or screenshot metadata. Bootstrap rejects malformed versions and
non-string/invalid keys; focused protocol checks include these cases. Parent owns
startup deadlines, cancellation and cleanup; blocking initial Java reads rely on
that owned-process deadline rather than claiming independent read cancellation.

ManaforgeUnityOpening reuses the existing auth/session/projection and hands native
IO to the serialized worker outside admission. The diagnostic accepts one opening
choice, emits submitted, waits for native transport acceptance and observed engine
advancement, emits conservative uncertainty, then waits for the owner lifeline.
It has finite accept/action/lifetime bounds. Saved-deck launch integration,
production listener lifecycle/containment and privacy acceptance remain pending.
The live report accurately leaves duplicate-test booleans false in Unity mode:
that run submits one choice, while the separate Java peer exercises duplicates.

The .132 scheduled CI check confirmed [.131 protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41261559681)
and [.131 preview](https://github.com/RyMeep128/Manaforge/actions/runs/41261559702)
success, plus prior live-opening success. The [.131 live job](https://github.com/RyMeep128/Manaforge/actions/runs/41261559717)
was still running and was deferred. Older native-helper CI failed because its
compiler glob pulled in the new gateway/protocol consumers without their classpath.
Its source list is now explicitly the three original bridge/server/metadata files;
focused local validation passed 147 native object checks, 11 pinned API inspections
and bridge compilation. This fixes shared build infrastructure without enabling
or changing mana policy. New CI evidence remains pending; next check is .135.

Principal files: ManaforgeUnityOpening.java and the diagnostic Java entry point;
LiveOpeningScene.cs and FoundationTable routing; the additive surface inspection-ID
accessor; tools/check_play_unity_live.py; bootstrap checks and native compile scope.
Generated Unity build-setting/scene rewrites are excluded. The Python/Qt fallback
and the owner's unrelated working-tree edits remain intact. G0/G1 and full-game
acceptance are still open. Stop here for owner UI review.
