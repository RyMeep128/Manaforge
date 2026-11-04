# Current roadmap

Manaforge remains in alpha development. This page records current direction;
completion requires evidence for the relevant revision, not an old checked box.
See [development and CI evidence](development-workflow.md).

## Desktop

Continue friend testing of installation and updates, deck creation and discovery,
recommendations, printing, offline use, and feedback. Preserve user-owned data
and compatibility while addressing observed failures. Use the [user guides](README.md)
for current workflows and [shared components](shared-components.md) for boundaries.

## Play

Unity is the gameplay UI; Java/XMage owns rules and decisions. Python remains for
deck/artwork preparation and process ownership. The Python gameplay adapter and
Qt game table are retired. Source Play offers one **Start Game** action for Unity;
installed builds retain the release gate.

Remaining acceptance includes current-revision Python/Core and protocol checks,
Java/XMage checks, licensed Unity checks, packaging, and playable saved-deck
human-versus-AI evidence. Fixture or opening success does not close that gate.
Owner visual review and documented coverage limits remain relevant.
See [Play development](play.md).

## Longer-term requirements

Private multiplayer, playgroups, broader game formats, and extensive product
requirements remain design references rather than completed features or new
implementation authorization. Their original acceptance criteria and the old
milestone checklist are preserved in the [archive](archive/README.md).
