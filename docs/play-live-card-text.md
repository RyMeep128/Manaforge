# Live card text

The live path is `CardView.getRules()` in XMage, `view_rules` in
`ManaforgeBridge`, `engine_view_text` in `ManaforgeOpeningProjection`, and
`ViewerCardSurface.DisplayRules` in Unity. A supplied `current_abilities` list
takes precedence, including an explicitly empty list.

Core artwork bundle version 2 also carries the exact face's printed name,
Oracle text and mana cost. Unity still accepts version 1 bundles. Printed rules
are used only when live abilities are unknown, engine view text is blank, and
the visible name and type match the admitted catalog face. XMage's hyphen and
Core's em dash type separators compare equally, with whitespace normalized.
Known copy, transformed and
flipped states reject this fallback. The inspection status labels it
`Printed rules (live text unavailable)`. Printed mana costs use the same face
check. This path currently depends on successfully admitted local artwork;
missing artwork does not supply catalog text independently.

## Packaged regression

Build the current Windows player, then run:

```powershell
./tools/unity-play.ps1 -Mode Build
python tools/check_play_rules_text.py --xmage-root <approved-pinned-bundle>
```

This uses the normal saved-deck launcher, authenticated viewer projection and
packaged Unity player with a real XMage AI seat. Three separate public decks
contain sixty identical copies so the shuffled opening always includes the
card under test: Foundry Street Denizen (GTC 92), Krenko, Mob Boss (M13 138),
and Krenko's Command (M13 139). Core catalog entries and cached artwork must
already be available locally; this check forbids downloads.

The opt-in UI driver handles pregame choices, inspects an opening-hand card,
records engine and displayed text, checks visible layout and the printed mana
cost, and captures the actual player framebuffer. It then closes through the
owned session lifecycle. Evidence is written under Unity's ignored `Artifacts`
directory. Inspect the PNGs as well as the JSON reports. This proves opening
card presentation, not a completed match or dynamic ability changes later in
play. PlayMode tests separately cover missing-text fallback, live precedence,
face mismatch, concealment, bundle pinning and text limits.
