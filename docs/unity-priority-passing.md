# Unity priority passing

Unity uses the existing `UnityPriorityPolicy`, `ViewerDecisionPanel`, and authenticated command dispatcher. XMage remains authoritative. A pass is always the single pass action on a current engine-issued priority offer. There are no synthetic decisions or phase-jump commands.

## Research and comparison

Wizards describes Arena's ordinary automatic passing, own-upkeep/end-step skipping, own-trigger skipping, and card-dependent exceptions in [Smart Priority, October 27, 2025](https://magic.wizards.com/en/news/mtg-arena/announcements-october-27-2025). Its [mobile controls documentation](https://magic.wizards.com/en/news/mtg-arena/mtg-arena-state-game-january-2021-01-21) also describes Full Control. Public official documentation does not comprehensively specify every desktop shortcut or exception. This implementation therefore provides the requested control modes without claiming to reproduce Arena's unpublished heuristics.

Before this change, Unity delayed each automatic pass by 350 ms, skipped all beginning-phase responses, supported only persistent Manual Control, and applied every stop on both players' turns. The older Qt controls described in play-priority-control.md were not the active Unity implementation.

The policy follows Arena-style defaults: own upkeep/draw/end-step and own-stack response windows normally advance, while empty own main phases await explicit progress. Opponent spells still offer responses during normally skipped own steps. Native Smart Priority facts restore important exceptions without a production card-name allowlist. Unknown or incomplete response information holds. The 99% parity target is a product goal, not a measured result; unpublished Arena behavior and long-tail mechanics require comparative gameplay evidence.

## Controls

- **Next / Pass / Resolve:** pass one authenticated priority opportunity. Space has the same behavior. Resolving still requires the other players to pass.
- **Pass until response:** Enter arms passing through the current turn until an opponent adds a stack object or permanent, or the turn changes. Own triggers do not cancel it. Meaningful or unknown responses stay held at the boundary; a proven pass-only window advances without an extra Resolve prompt.
- **End turn:** the normal click uses Pass until response, so a new opponent response interrupts it. **Pass Turn** is the explicit force mode (Shift+Enter, Shift-click, or the menu's ignore-responses option). Required choices and configured stops always interrupt both modes. Until my next turn remains a separate option.
- **Resolve All:** pass through the current stack, stopping when it empties or a new object appears. Minimized stack controls remain accessible.
- **Full Control for this phase:** Ctrl toggles a temporary hold through the current phase and turn, with a hold at the next actual priority opportunity after that phase. If armed before a phase is known, it attaches to the first observed phase.
- **Hold Full Control:** Shift+Ctrl toggles persistent manual priority. It stays enabled until switched off. Starting an explicit yield deliberately leaves Full Control.
- **Stops and settings:** separate phase and individual-step checkboxes for your turn and opponents' turns, including combat steps. Stops are one-time by default and retire after their phase/step visit. Repeat stops every turn makes newly selected stops persistent. The phase strip scopes stops to the turn currently displayed.

Keyboard commands do not answer required choices and are suppressed for text entry, layout editing, and the game menu. Mouse controls remain available. Ordinary auto-pass defaults on; Full Control, yields, and stops default off for each new viewer/session.

## Scheduling and failure behavior

The per-opportunity timer is removed. After presentation holds, the next Unity tick may claim exactly one engine pass. Dispatch still checks current offer identity, revision, viewer, submission reservation, and command acknowledgement. The scheduler never loops over imagined future opportunities. Required targeting, combat, payments, ordering, numeric input, and ability selections are never automatically answered by this policy.

Flow: Unity panel -> ViewerCommandDispatcher / ViewerDecisionBinding -> ClientSessionChannel reservation and serialized write -> Java OpeningSession / GatewaySessionBoundary / SubmissionLedger -> projection claim -> GameplaySession -> bridge native response -> XMage -> native evidence and acknowledgement -> fresh projected offer. Observation snapshots carry no decision authority.

Stale offers cannot submit. An attempted decision is not retried automatically. Rejections, uncertainty, disconnection, and terminal states cancel yielding and suspend automation; Resume permits consideration of fresh offers. Uncertain commands are not resent. Concession has its own tracked reservation so it remains available while waiting for another command or another player's priority.

A confirmed receipt atomically retires its matching decision under the channel admission lock. The old offer cannot reopen between confirmation and the following snapshot, and a late receipt cannot retire a newer offer. Local stale-decision failures proven to occur before writing do not pause fresh offers or trigger retries; actual remote rejections and uncertain writes still suspend automation.

## Other gameplay fixes and deployment

Client changes include the persistent stack panel, damage assignment drawer restoration, terminal Escape menu, readable red damage, named counter badges, artwork face selection, and priority controls. Host Java changes publish public state while waiting, enrich observer metadata for commanders/organization/artwork, and improve general automatic-payment safety. The Python launcher retains lobby seats, decks, and invitation after results or game interruption while requiring fresh readiness. Both installations should update for the full set; no relay service code changed.

Physical-copy artwork uses the original physical printing while current rules and characteristics remain those of the copy. This fixes original inspection; a separate borrowed-art texture for the live copy is not implemented here. Ability art uses the source printing rather than treating the ability label as a printed card face. Unsupported or unavailable catalog artwork still falls back safely.

## Validation

Use tools/validate_unity_local.ps1 for Unity tests, graphics, player build, and gameplay acceptance, plus tools/unity-play.ps1 -Mode Build after Unity changes. Python/Core, Java/XMage, and protocol suites belong on GitHub Actions. Uncommitted work has no exact-SHA hosted evidence. Consult the local validation report for stages actually completed; a build or fixture pass is not full multiplayer acceptance.

For diagnosis, `tools/validate_unity_local.ps1 -PlayModeFilter <full-test-name>` runs a focused regression and writes a scoped report. It does not build/archive a player or claim full gameplay acceptance. Finish with the default full validation run.

## Smart Priority mechanics

The host reads presentation facts under the existing native pause/cycle guard. `priority_hints` is an optional bounded enum list; `priority_object_id` is the viewer-local opaque reference for the native top stack object. Missing facts preserve meaningful response windows. No native ID or new command authority crosses this boundary. Unity still sends only an engine-offered pass.

| Situation | Behavior |
|---|---|
| Ordinary own upkeep, draw, end step, or response to own object | Advance unless an override or smart exception applies |
| Empty own first or second main phase | Hold for explicit Next or a selected yield |
| Opponent spell/ability on the stack | Offer meaningful responses on either player's turn |
| Own trigger will sacrifice/exile its source | Preserve a meaningful response before it leaves |
| Final Saga chapter | Hold available actions, including basic mana, before the source is lost |
| Own end-step untap trigger | Hold available mana/actions before untapping; floating mana keeps an end-step opportunity open |
| Own instant/sorcery with a copy effect in hand | Preserve a response to the original spell |
| Public opponent draw/life-loss or draw/damage trigger | Preserve an own-upkeep response before drawing |
| Own permanent enters/returns during own end step | Preserve its newly available native activation |
| Opponent permanent enters during own end step | Preserve a meaningful response before the opponent untaps |

Stack-based exceptions hold once per correlated stack object. The exact decision remains held across UI ticks. After the player uses/passes that opportunity, a new decision for the same object does not repeatedly rearm it. More elaborate untap/reuse sequences require Full Control, matching Wizards' Saga example.

Typed native abilities and effect families cover source departure and Saga chapters. Generic native English rules identify additional draw, untap, and spell-copy mechanics; these are presentation heuristics, not legality calculations. Unpublished Arena exceptions, unusual custom rules text, repeated extra upkeeps, and mechanics without an observed public transition require comparative verification. Full Control and stops always override automatic behavior.

Coverage includes both turns, ordinary versus explicit passing, native smart facts, own/opponent stack additions, phase and step stops, temporary-control boundaries, one-time/repeating stops, cancellation during observation gaps, stale decisions, required choices, floating mana, and end-step arrivals. Native probes cover generic sacrifice effects and real Saga, untap, draw-hazard, escape-sacrifice, and copy-spell abilities; they execute on hosted non-Unity CI only.

For a diagnostic-only acceptance correction, `./tools/validate_unity_local.ps1 -ResumeAt authenticated-ui` rebuilds the Windows player and runs the authenticated fixture plus remaining multiplayer stages. `-ResumeAt multiplayer` starts at relay acceptance. Reports explicitly mark earlier stages skipped; these continuations must be read alongside prior evidence and never produce a full release acceptance archive.
