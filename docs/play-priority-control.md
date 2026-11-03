# Automatic priority and Full Control

Status: implementation ready for CI; engine acceptance and manual UX sign-off
are pending. This feature was absent from build 0.5.28-alpha.1.

Automatic priority defaults on. It submits the current engine-offered pass only
when the local player owns an explicit priority opportunity, action information
is complete, and no meaningful action, game choice, stop or control hold exists.
Basic mana abilities alone do not stop it. Unknown actions, special-action
metadata gaps, stale frames and unsupported state hold priority. The UI reports
why it is holding. XMage continues to own rules, legality, phases and AI.

## Turn boundaries

Automatic and Pass Until Response always stop on an empty stack in your
postcombat main phase. Click the dedicated **End Turn** button to pass that
opportunity toward the end step. This is one engine pass, not a phase jump: an
opponent can respond, and returning to postcombat main requires another explicit
End Turn. Automatic passing also stops on your empty end step; explicitly pass
there to finish your turn. Space and Enter cannot dismiss either boundary.
Rules that skip a step or grant no priority cannot be overridden by this UI.

## Controls

- **Pass Priority:** one current engine opportunity.
- **Pass Until Response:** pass uninteresting priority this turn; meaningful
  actions, game decisions, stops and turn boundaries interrupt it. Cancel passing
  cancels the queued pass and holds the next eligible opportunity, even when
  default Automatic is on.
- **Full Control:** hold every actual priority opportunity until disabled,
  including responses to your spells and triggers.
- **Hold next priority:** may be registered before that window. It remains until
  you explicitly handle a priority opportunity and the engine advances to a new
  one; submission alone is not confirmation.
- **Phase timeline:** click a step to schedule/remove a stop on your turn or
  other players' turns. One-time stops hold that step's window and then expire;
  the menu can make newly scheduled stops recurring for this match.

Automatic and persistent Full Control preferences use existing QSettings under
Manaforge/PlayPriority, keyed by local seat. Match holds, passes and stops are
never persisted. The policy stores independent state for any number of seats;
the current offline UI remains one local human versus one AI. It never reads or
commands an AI seat. Stops currently distinguish your turn from all other turns,
rather than selecting one named opponent in a multiplayer UI.

Default shortcuts: Space passes once, Enter enables/cancels Pass Until Response,
Ctrl holds next priority, Ctrl+Shift toggles persistent Full Control. Change them
in Priority controls > Configure shortcuts. Shortcuts ignore text entry and
other dialogs. Holding modes can be registered while a command is pending.

## Command safety and verification

The pure PriorityController returns an offered action; PriorityControls schedules
it on the UI event loop and rechecks holds immediately before calling the public
SessionController. The session's exact-frame, seat, decision, busy and stale-token
guards still apply. A decision is attempted automatically at most once. No
replay occurs after rejection or uncertainty; automation pauses until a new
match. Polling, menus and modal dialogs defer a scheduled pass rather than losing
it. Leaving or closing a match cancels queued UI work.

New CI coverage includes policy, two-to-five-seat independence, scheduling,
keyboard boundary guards, preferences, metadata completeness, unknown actions,
optional/mandatory choices, stops and stale/duplicate protection. The real-engine
`priority` acceptance scenario checks retained engine decisions and subsequent
engine advancement using the production policy and public adapter. Existing AI,
Commander and UI scenarios remain enabled. Explicit UI fixture pilots select
Full Control so scripted clicks do not race automation.

No routine tests, local Java builds or local engine acceptance were run for this
story, as requested. Lint, formatting and diff checks are local static checks.
CI results must be reviewed before calling the story complete. Direct real-engine
priority acceptance currently targets two human fixture seats; multiplayer policy
coverage is not proof of three-to-five-player engine automation or AI behavior.

## Next-build manual review

1. With Automatic enabled, play a land and check that mana-only priority windows
   progress without clicks. Verify instants and activated abilities retain control.
2. Toggle Full Control, cast a spell and respond to it; disable Full Control again.
3. Hold Ctrl during the opponent's turn or while your command is pending; verify
   the next granted priority is retained until you explicitly act.
4. Add upkeep/end-step stops for your and other turns; review one-time and recurring
   behavior. Toggle Pass Until Response and cancel before its next scheduled pass.
5. Reach postcombat main: confirm it waits for End Turn, then waits again in the
   empty end step. Confirm Space/Enter cannot finish those boundaries.
6. Test targeting, optional payments, attack/block declarations, card inspection,
   text fields, settings persistence, close and cancellation. None may be answered
   by priority automation.
