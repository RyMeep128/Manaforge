# Arena-inspired library, graveyard and exile

Owner visual review: **PENDING**. This increment extends the live Arena view on
`codex/play-live-first-land` in `C:/Users/ryanm/Proxy App/arena-visual-continuation`.
The other integration worktree and its unfinished artwork/text changes are untouched.

## Arena investigation

Wizards' [January 2021 gameplay overview](https://magic.wizards.com/en/news/mtg-arena/mtg-arena-state-game-january-2021-01-21)
explains that zone interaction opens a browser containing known cards and the
zone count. Its [official battlefield screenshot](https://media.wizards.com/2020/images/daily/m7g4ren4_battlefield_shot.png)
was inspected for small card-shaped piles beside the hand, card backs and
face-up zone presentation. The reference is mobile; Manaforge adapts the interaction
for desktop pointer and keyboard input rather than claiming pixel-identical layout.
The downloaded reference stays in ignored `Artifacts/ZoneReferences`; it is not a
runtime dependency or redistributed asset. Existing local imported card-back art,
fonts and shared card rendering are reused; supplied originals remain unchanged.

## Behavior

Each player has a library, graveyard and exile pile beside their battlefield.
The library uses a card back and the existing authoritative library count. Public
piles show the number of viewer-visible cards and borrow a visible card's artwork
when available. The preview is representative: the protocol does not certify a
top-card/order relationship, so the client does not infer one. Missing art retains
a readable projected-name fallback. Empty piles remain discoverable.

Click a pile or focus it and press Enter to open the browser. Library, Graveyard
and Exile tabs retain that player's scope. Full-proportion shared CardViews can
be hovered, inspected and paged. Esc or Back to battlefield closes the browser.
Piles are hidden during the generous opening/mulligan overlay to avoid covering
hand cards. Normal ranks reserve a left-side zone rack. Confirmed library-to-hand
movement starts from the new actual library position and still honors reduced motion.

Unrevealed library cards are represented by a back and a count, not invented card
objects. Even the local saved deck is not used to reconstruct its remaining
library. Only cards currently admitted by the authenticated viewer projection
appear in a browser. Hidden and face-down objects are excluded from face previews.
A normal hidden library therefore correctly says e.g. 54 cards, 0 known.
Graveyard/exile counts describe visible objects; absent public total-count fields
are not reconstructed from concealed objects or guessed from deck contents.

When a current engine decision offers only visible cards from one of these zones,
the matching browser opens automatically. It makes no selection. Click/Enter or
a drag of an offered card uses the existing ViewerDecisionPanel binding and exact
current token. Drag options are accepted only after release in the existing play
area. Ambiguous choices remain explicit, and selection never auto-finishes a
prompt. Casting from a graveyard/exile works only when supplied as a legal action.
There is no arbitrary Draw, Move, Return or Exile command, and cards remain in
their projected zones until the engine confirms a change.

## Ownership and privacy

The surface owns the actual CardViews and textures. Pile Image elements only borrow
admitted visible artwork; they do not load assets or create a second game-state
model. Surface rebinding clears these references before any card's visibility or
printing changes; viewer clearing releases them before scope-owned textures are
disposed. Browser cards stay under the same surface owner. No protocol, deck model,
Card Database, Deck Editor, Printer, rule service or online runtime dependency changes.

## Verification and reproduction

```powershell
Set-Location 'C:/Users/ryanm/Proxy App/arena-visual-continuation'
./tools/unity-play.ps1 -Mode Build
python tools/capture_play_visuals.py
```

The capture command uses the existing opt-in strategic driver in a real packaged
saved-deck XMage 1vAI match. Normal launches do not mount the driver. It now captures
library-browser.png, exile-browser.png and public-zone.png as well as the board,
opening, combat, hover/inspection, draw and result states. This is packaged evidence,
not a mocked projection claiming native gameplay.

Windows build succeeded. The first packaged iteration at
`Mtg_Projects/mtg_play_unity/Artifacts/ArenaVisualReview-e2aeccae` completed a native
loss with 155 snapshots, 154 confirmed inputs, zero uncertainty, viewer cleared and
cleanup confirmed. Its three browser captures and battlefield pile rack were
visually inspected. The opening capture prompted the opening-overlay pile fix.

Focused CI tests were added/updated for hidden-library browsing, empty exile,
viewer/zone validation, offered known-library browser opening, exact drag option
tokens and no command before release. Local test suites were not run, following
AGENTS.md; these tests require Actions verification. Existing historical 50-test
results in the earlier visual-review document are not results for this increment.
The persistent checkpoint retains its original pending baseline SHA; missing
GitHub CLI continues to block exact workflow/job/step evidence. No promotion or
release is authorized by the patch bump.

## Manual review still required

- [ ] Both players' piles and counts at all four target resolutions.
- [ ] Click, Enter, tabs, Esc, hover and full inspection.
- [ ] A native library-search/reveal decision with cards supplied by the engine.
- [ ] Native graveyard/exile selections and casting, including cancellation.
- [ ] Face-down exile and library privacy after visibility changes and disconnect.
- [ ] Large visible zones and pagination, source-only rendering and reduced motion.
- [ ] Commander side-zone spacing; the primary verified layout remains ordinary 1vAI.
- [ ] Owner visual approval and required Actions results.

An empty-exile capture proves the browser/empty state, not an exile spell resolving.
Known-library search and exile-casting scenarios remain separate native acceptance
items. Opponent artwork and current rules/mana coverage retain the branch's existing
projection limitations; no hidden identities are filled in by card-name guesses.

Final packaged evidence follows after the final rebuild.

## Final packaged evidence — 0.5.223-alpha.1

Final directory:
`Mtg_Projects/mtg_play_unity/Artifacts/ArenaVisualReview-7bf3cedf`.
Native win, 130 snapshots, **129 confirmed inputs**, zero uncertain, viewer cleared
and cleanup confirmed. Spatial proof records **49 card keyboard inputs**.
The final opening capture shows the pile rack hidden behind the mulligan overlay;
normal play shows all six piles. library-browser.png shows the authoritative
54-card library with zero known faces. public-zone.png shows an actual graveyard
card through the shared renderer; exile-browser.png shows the empty visible-exile
state. These captures were visually inspected. Actual 1366x768, 1920x1080 and
2560x1440 framebuffer requests match their observed sizes; baseline is 1280x720.
Windows non-development player build and diff whitespace checks passed.

The package uses the normal authenticated saved-deck path with the explicit
public-deck acceptance driver. It is not proof of a manual search decision,
face-down-exile scenario, arbitrary card casting or human visual approval.
Required Actions and owner review remain pending. The existing pending baseline
SHA is retained rather than replaced by the new development HEAD. No main merge,
release or tag is made.
