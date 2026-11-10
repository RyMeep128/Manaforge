# Unrestricted Commander

Choose **Unrestricted Commander** in Play's Format selector. Use the saved deck's
commander selections (or its Commander section); the editor's Commander selection
and deck checks dialog permits any card, including instants, as a commander.

This mode uses the pinned engine's **Freeform Unlimited Commander** game and
validator. It retains Commander gameplay: 40 starting life, the command zone,
commander tax, commander damage and native commander zone-change decisions.
It imposes no deck size, singleton, color identity, ban-list, commander card-type
or partner-eligibility restrictions. A 300-card deck with an instant commander
and duplicate banned cards is allowed when those cards are implemented.
Saved decks and their artwork are preserved.

Every active card must resolve to an implemented engine card before starting.
Unsupported or unresolvable cards block launch; legality data does not. Invalid
saved-document references, malformed quantities and transport/resource limits
remain runtime integrity checks rather than format rules. A designated commander
is not required, and a commander-only deck is not rejected for deck size.
The current Play launcher supports one human versus one AI.

Only designated commanders are sent to the native command-zone initialization.
Undesignated sideboard cards do not become additional commanders or enter the
main deck. Saved companion selections do not block this mode; companion pregame gameplay
is not enabled, and an undesignated sideboard companion stays out of the game.

CI covers readiness versus ordinary Commander, preservation of large deck
manifests, cross-language launch fixtures, the format selector, and native
acceptance of duplicates/banned cards with an instant initialized as commander.
These checks do not claim that every implemented card interaction is supported by
the player UI. Hosted packaged acceptance remains subject to Unity licensing.
