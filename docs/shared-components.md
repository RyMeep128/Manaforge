# Shared components and domain operations

Before implementing new UI or business logic, search for an existing implementation.
Extend or reuse it whenever appropriate. Shared functionality should have a single
authoritative implementation so fixes propagate across the application.

## Preferred implementations

- `mtg_ui.card_chrome`: painted quantity controls, corner counts, and vertical
  button geometry. `mtg_ui.quantity_preview.QuantityPreview` adapts this chrome
  to a QLabel preview and emits quantity requests; it never changes a deck.
- `mtg_editor.canvas.CardCanvas`: shared deck/search canvas, also inherited by
  recommendation and commander discovery canvases. Use its quantityRequested
  signal to connect a feature container to its command.
- `mtg_core.deck_mutations`: `apply_quantity` for absolute quantities,
  `change_quantities` for selection deltas, `remove_entries` for removal,
  `add_card` and `change_candidate_quantity` for discovery's one-copy actions.
  These functions mutate a DeckDocument without importing Qt. Call them inside
  the editor's `edit` transaction so history, refresh, and persistence remain
  the container's responsibility. Card details re-exports `apply_quantity` for
  existing consumers; new consumers should import from core.
- Search, Quick Add, recommendation panels, Discover Deck Ideas, and commander
  discovery connect to the editor commands rather than modifying deck entries.
- `mtg_core.decklists.apply_decklist` retains import-specific quantity merging,
  artwork matching, and section preservation. Discovery adds one mainboard copy;
  an import can add many copies to another section. Do not conflate these policies.

Discovery removal prefers mainboard over commander copies, then the requested
printing, then sort order. It does not depend on the editor's selected cards.
A quantity reaching zero removes the entry and commander/companion references.
The caller supplies any legality checks or workflow-specific confirmation.

## Audit scope and remaining opportunities

The repository review covered quantity controls and mutations, deck import,
commander selection, card details, discovery consumers, and existing shared UI
helpers. Existing shared chrome and the canvas hierarchy already eliminate much
of the visible duplication; this change extends those implementations.

Text rows retain horizontal compact quantity controls. Print-project controls
retain their project-model callbacks. Commander selection splits owned copies,
and basic-land management tracks generated copies: these are distinct operations
and retain their domain rules. Import merging also remains a separate policy.

Further candidates for focused follow-up include background metadata-loading
workers in card details and discovery, repeated discovery result preparation,
and legacy print/proxy compatibility adapters. Evaluate cancellation, model, and
artwork differences before merging them. This is an incremental consolidation,
not a claim that every duplicated behavior has been eliminated.

Regression tests live in core's `test_deck_mutations.py` and the editor's
`test_add_card_quantity_ui.py`; existing editor tests cover undo integration.
