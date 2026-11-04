# Automatic priority in Unity

This implementation targets the active Unity Arena gameplay path. It supersedes the earlier Qt-only priority patch for normal matches.

The top-right Unity priority panel starts with **Auto-pass priority** checked and **Manual control** unchecked. No phase or step stops are selected. Settings and temporary yields belong to the current viewer/session; a new game starts fresh.

Ordinary automatic passing waits 350 ms, then submits the current engine-provided pass action only when this is a genuine priority opportunity. During the beginning phase it passes upkeep/draw priority even when responses are available, stopping at the main phase. In other phases the engine's complete action list must contain no non-pass action. Available actions (including mana activations) and incomplete information preserve the prompt. Empty rendered controls alone never prove there is nothing to do.

- **Manual control** cancels a yield and holds every priority opportunity until unchecked.
- **Yield / phase stops** expands the controls; automation pauses while they are open.
- Beneath **Pass priority**, **End turn** yields through the current turn and stops when the next turn starts, including an extra turn. On opponents’ turns the button reads **Pass to my turn** and yields until your next turn begins. Both respect phase/step stops and leave required choices manual; completing those choices preserves the yield. The button requires a current actionable priority offer.
- **Yield until my next turn** explicitly permits passing available responses until the viewer's next turn begins.
- **Yield until stack changes** explicitly permits passing available responses until stack membership or order changes. Opaque stack references remain stable while continuously present and retire on removal.
- **Cancel yield** ends the explicit yield; the ordinary auto-pass checkbox still applies.
- Phase and step stops apply on both players' turns and override all automatic modes.
- Rejected, uncertain, or failed commands pause automation. **Resume automatic passing** allows reconsideration of a fresh decision; an already-attempted decision is never automatically retried.

Targets, combat assignments, payments, trigger ordering, numeric input, and other non-priority choices remain manual. Existing authenticated offer identity, command tracking, and native submission validation remain authoritative. Late command failures are monitored even after the displayed offer is replaced. Viewer changes, completion, disconnect, and disposal cancel pending automation/yields. Engine desktop phase-skipping preferences are disabled so Unity receives priority opportunities needed for stops and manual control.

## Live card updates

Ordinary snapshots retain unchanged artwork bindings and open inspection. Artwork is cleared when visibility is revoked or its identity changes. Creature stats show current power and current toughness minus marked damage; this is a display adjustment only. Each value is green above its engine-supplied original/base value, orange below it, and normal at base. Unknown or symbolic comparisons keep normal color. Damage cleanup restores the displayed toughness.

Regression coverage lives in the Unity card/surface and priority tests and the Java projection checks. Run suites through GitHub Actions and verify checks against the implemented commit SHA; uncommitted changes have no exact-SHA CI evidence.
