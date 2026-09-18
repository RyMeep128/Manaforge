# Card layout support

Manaforge keeps Scryfall's rendered card image intact. Layout names describe how
that image is imported; print footprint remains a project choice through **Print
oversized**.

| Card layout | Import and rendering rule |
| --- | --- |
| Transform and modal DFC | Import both face images, link the matching back, and render the back in the mirrored front slot. |
| Battle | Scryfall represents battles as transform cards, so the DFC rule applies. |
| Double-faced token, reversible card, and art series | Import and link both independently imaged faces. These all match Scryfall's `is:dfc` filter. |
| Meld | Import each meld component as its own card; relationships remain available through related-card suggestions. |
| Split and aftermath | Use Scryfall's complete combined card image in one slot. |
| Adventure and flip | Use the complete card image in one slot. |
| Plane and scheme | Preserve the landscape artwork in one slot unless the user enables **Print oversized**. |
| Token | Use one slot; double-faced tokens follow the DFC rule. |
| Custom or unknown | Use one front image and the normal one-slot footprint. A user-selected custom back and oversized setting still apply. |

Every one-slot layout can be marked oversized, which uses the existing rotated
two-horizontal-slot footprint. Unknown future layouts use the custom fallback
instead of guessing a new physical size.

For an unknown layout with several independently imaged faces, Manaforge imports
the first available face as the front. It does not infer a back, add extra copies,
or reserve more than one slot. The user can then choose a custom back or enable
**Print oversized** explicitly. This keeps future Scryfall layouts printable while
avoiding an incorrect physical arrangement.

Oversized behavior is consistent across the matrix: the copy consumes two
adjacent horizontal slots, cannot be placed in a one-column sheet or across a
row boundary, and its linked or custom back mirrors the complete two-slot
footprint. This setting survives project save and reload.
