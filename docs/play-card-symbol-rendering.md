# Cost and inline rules symbols

Owner visual follow-up, October 30, 2026: mana glyphs were still displaced inside
their pips, and rules such as `{T}: Add {C}{C}.` appeared as literal notation.

ManaSymbolView now uses actual font glyph bounds for placement, with a centered
textured quad inside the disk. This avoids centering the font's entire line box,
whose baseline differs from the visible symbol. Glyphs share the existing pinned
Mana font at one raster size; zoom scales geometry rather than adding arbitrary
font sizes. Attached views repaint on shared atlas rebuild and detach their
subscriptions when removed. The font and its license remain unchanged.

The same component renders rules-text tap `{T}`, untap `{Q}`, colorless `{C}`,
colored/generic/variable mana, snow, Phyrexian, energy and two-part notation already
recognized by the formatter. This only displays supplied tokens; it computes no
mana, legality, payment, activation or outcome. Full authentic-image fallbacks
remain untouched because their symbols are part of the printing image.

RulesTextView uses bounded word/symbol runs and literal labels with rich text
disabled. Unknown tokens remain literal; oversized runs fall back to the intact
native text label rather than creating unbounded elements. The original supplied
rules string stays exact. The native label is visually replaced only when inline
symbols are active; plain rules retain native layout. Conceal/rebind removes old
runs and atlas subscriptions along with the original card text. This is initial
inline flow, not complete card typography or every possible symbol treatment.

Review fixture: `Artifacts/SymbolReview-20261030` contains public Sol Ring,
Counterspell, Forest and Grizzly Bears examples. It is printed mock data with no
engine connection or deck read. Launch it with the existing artwork fixture
argument and use Inspect to compare the four cards. Owner visual review remains
required before declaring alignment accepted.

Implementation references: Unity's
[CharacterInfo bounds](https://docs.unity.com/en-us/engine/6000.6/script-reference/unityengine/characterinfo)
and [textured mesh UV handling](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/UIElements.MeshGenerationContext.Allocate.html).


Validation passed: 254 focused EditMode checks, five PlayMode checks, the Windows
build and packaged Sol Ring/Counterspell review captures. The attached-panel check
also requires inline symbols to occupy the first text line rather than the middle
of the entire rules box. Captures were inspected for centered cost glyphs and
visible tap/colorless symbols; owner aesthetic approval remains pending. No full
application suite ran. CI is checked at this third-commit checkpoint without
waiting for unfinished runs.
