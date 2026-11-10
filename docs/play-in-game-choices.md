# In-game choice support

Implementation scope: 0.6.33-alpha.1, against the pinned XMage 1.4.62 runtime.
This is a capability inventory, not a claim that every card or packaged scenario
has passed acceptance. Sideboarding and deck construction remain outside this work.

| Native decision | Gateway behavior |
| --- | --- |
| `GAME_ASK` | Explicit yes/no responses. |
| `GAME_SELECT` | Priority, attacker/blocker declarations, and non-priority selections with an explicit native legal-target list. Card views alone never establish legal options. Other selection variants retain an unsupported diagnostic. |
| `GAME_TARGET` | Native offered targets, library choices, and optional finish, including zero candidates when the engine permits finishing. |
| `GAME_CHOOSE_ABILITY` | Engine-supplied ability options, bounded to 32 entries. |
| `GAME_CHOOSE_CHOICE` | Engine-supplied strings/keys, including modes and ordering choices. |
| `GAME_GET_AMOUNT`, `GAME_GET_MULTI_AMOUNT` | Native numeric constraints and explicit numeric input. Ordinary X selection uses this path. |
| `GAME_PLAY_MANA` | Java-owned ordinary Auto payment and native manual payment; consequential or unverified costs retain manual input. |
| `GAME_CHOOSE_PILE` | Two piles with viewer-authorized previews, explicit selection, and separate confirmation. Either pile may be empty. |
| `USER_REQUEST_DIALOG` | Explicit hand-visibility and rollback consent, using the native request's buttons and whitelisted native actions. Other request kinds produce a nonfatal notice. |
| `GAME_PLAY_XMANA` | Legacy compatibility gap. The callback and server sender exist, but the inspected pinned human-player implementation has no identified emitter. Do not conflate this with ordinary numeric X selection. |
| `SIDEBOARD`, `CONSTRUCT` | Deferred match/lobby flows. |

Updates, redraws, personal information, errors and game-over callbacks are not
selectable decision families; existing visibility and lifecycle handling still apply.

## Piles and privacy

Optional `ChoiceRequest.groups` binds each pile to an existing opaque option.
Each preview contains only the engine-authorized name, type and view rules;
concealed cards retain their concealment flag and no identifying fields. Native
card IDs are not exported in pile metadata, and previews grant no command authority.
Both consumers validate group/option binding. Each pile is limited to 256 cards;
the UI pages previews to avoid mounting an unbounded number of card views.

## Permission requests

Optional `ChoiceRequest.request` identifies a separate modal request. Incoming
requests do not overwrite the bridge's native gameplay decision. The serialized
owner publishes a new viewer revision while waiting between complete frames,
pauses gameplay submissions, and validates the request again before replying.
After a reply or expiry it obtains a current, guarded engine context and republishes
gameplay. Auto mode reassesses any remaining payment rather than requiring manual
rescue. Manual and Full Control retain their existing behavior.

No permission is granted automatically. Requests expire after two minutes, are
bounded to 16 pending entries, replace older duplicates, and cannot be replayed.
For the pinned hand-visibility dialog, Reject has a null native action and sends
no gameplay response. Rollback Deny uses the supplied native denial action.
Acknowledgement confirms delivery of the explicit reply, not that a rollback or
visibility transition has completed. Those outcomes remain engine-authoritative.

Optional snapshot `decision_error` and `session_notice` carry safe diagnostic
codes. An unsupported optional request is distinct from an unsupported required
gameplay choice and from a manual-payment fallback. No private prompt payloads,
native user IDs or request-routing tokens belong in public diagnostics.

These are additive optional protocol-1 fields; older fixtures without them remain
valid. Unused new fields are omitted from ordinary gateway snapshots so an older
strict player can still consume existing choices. The new choice types require
the rebuilt player. Generated Java/C# models and both validators change together.

## Evidence and acceptance

GitHub Actions owns all test suites. Coverage includes shared DTO/privacy fixtures,
both pile responses, stale options, empty piles, explicit target lists, consent
admission/expiry/no replay, idle-only owner polling and bounded partial frames.
The native permission adapter checks use a transport fixture and do not establish
a real networked permission outcome.

Hosted Unity acceptance adds real Fact or Fiction games selecting either pile and
verifying the destinations of all five revealed cards, plus X=0, positive X,
cancellation, search and modes. The existing ordinary Auto and normal shuffled
human-versus-AI acceptance gates remain mandatory. Missing Unity licensing blocks
packaged evidence; compilation or helper success is not a substitute. Full
networked consent outcome acceptance remains a separate required verification.

Preserve logs and existing build-generated workspace changes. Rebuild the local
player from a verified source SHA after CI review, recording source and build
provenance. Until that rebuild, the existing player retains its earlier UI.
