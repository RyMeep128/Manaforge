# Unity Play

Unity is the gameplay UI and Java/XMage owns rules and decisions. Python handles
saved-deck and artwork preparation, pinned engine provisioning, and process
startup/cleanup. The Python gameplay adapter and Qt game table are retired.

## Start a game

1. Build the Windows Unity player using the [Unity project guide](../Mtg_Projects/mtg_play_unity/README.md).
2. Open Manaforge from source and select Play. Choose Freeform or Commander,
   your saved deck, the AI opponent's deck, and a mana-payment preference.
3. Click **Start Game**. Close the Unity window to end the session. Closing
   Manaforge also requests cleanup of its owned game processes.

Returning to Play reloads saved decks. The desktop has no separate Python game
or Unity preview launch buttons. Diagnostic preview tooling remains available to
developers. Installed builds retain the release gate; the source override is
`MANAFORGE_ENABLE_LOCAL_PLAY` (enabled by default).

## Acceptance and references

Use [the development workflow](development-workflow.md) for exact-revision CI
requirements. The Unity workflow is manual and requires a licensed owner-controlled
runner. Python/protocol checks, Java opening checks, fixtures, and historical local
reports each cover only their stated scope. Full playable acceptance, packaging,
and owner visual approval must be assessed separately.

| Topic | Reference |
| --- | --- |
| Launcher modules and ownership | [Play package](../Mtg_Projects/mtg_play/README.md), [launch lifecycle](play-launch-lifecycle.md), [launch manifest](play-launch-boundary.md) |
| Cross-language contracts | [Protocol index](../Mtg_Projects/mtg_play/protocol/README.md) |
| Live engine implementation journal | [Live integration](play-live-integration.md) |
| Payment and priority | [Payment coordinator](play-payment-coordinator.md), [priority behavior](unity-priority-passing.md) |
| Engine pin and card coverage | [XMage fork](play-xmage-fork.md), [card support](play-xmage-card-support.md) |
| Visual review | [Arena review](play-arena-visual-review.md), [renderer measurements](play-renderer-benchmarks.md) |
| Original plans and acceptance criteria | [Archive](archive/README.md) |

The implementation references describe individual increments. Their versioned
status statements and historical pass counts are not current-revision sign-off.
The [documentation index](README.md) lists the remaining renderer, artwork,
session, and diagnostic references.
