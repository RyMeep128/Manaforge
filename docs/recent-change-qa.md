# Recent-change regression scenarios

Local tests, linting, formatting, and runtime validation were intentionally not run. CI/CD owns validation. Existing tests were left unchanged; the already-started Moxfield pagination test is included with the in-progress work.

Manual acceptance scenarios:

- Type into Quick Add without Enter, open Card Search, and confirm the query and results carry across. Edit in either field and confirm synchronization. Explicit syntax opens Syntax Search and retains its meaning; advanced filters remain separate. Editing invalidates Enter-to-add readiness.
- Discover from a card and add several results. Quantities update without resetting results, selected card, face, or scroll. Changing seed, tab, deck, format, legality, or EDHREC audience refreshes discovery.
- Change themes, legality, discovery selection, audience, recommendations, and guidance, then undo/redo. Semantic choices restore while zoom and scroll remain current.
- Remove a land and confirm automation stops. Undo restores automation and recomputes derived quantities; redo stops it. Manual copies remain intact.
- Unknown Commander colors or unavailable legal basic metadata leave automation enabled and waiting. Illegal Wastes are never added. Known legal colors and completed catalog metadata resume derived land allocation without an extra undo step.
- A targeting restriction such as ?target creature with flying? does not grant flying; actual grants and token creation with keywords remain recognized.
- Open Themes with a legacy discovery theme selected and save unchanged. The selection survives. Compact stack headers retain space for names/counts beside the expansion button.

Known CI interpretation conflict: one existing test still expects the removed empty-deck redirect. A failure of that expectation requires review against the intended new behavior; it is not by itself evidence that the redirect should be restored.

## Commander Oracle tag themes and face animation

Validation is deferred to CI/CD and manual review; no local tests, linting, formatting, or runtime checks were run. Existing tests remain unchanged.

- Open Themes with one commander, then with partner commanders. The Commander Oracle Tags group contains the union of locally available tags, with no duplicate options. Missing tag data shows an explanation and permits manual entry.
- Enter a tag or `otag:tag`, with surrounding whitespace or different casing. Add Theme selects exactly one option. Empty input is rejected without closing the dialog. An unknown tag can be saved but matches no cards until matching local tag data is available. Cancel discards edits.
- Select several tags and Save. Reopen the deck, change commanders, and undo/redo: selected custom themes survive, use match-any behavior, and retain exact tag meaning. Opening and saving unchanged preserves legacy selections.
- Check a custom tag against cards that share only its name, role, keyword, or a similarly punctuated tag: these must not match unless they carry the exact Oracle tag. Test quotes, spaces, and operator-like text as literal tag values, never injected search syntax.
- Discover Deck Ideas exposes saved custom tags under Commander Oracle Tags. Changing selected custom themes refreshes discovery. Custom options use local tag queries and never EDHREC membership statistics; active format and Commander identity restrictions still apply. Recommendation filtering uses enriched candidate Oracle tags and the existing legality pool.
- Flip a double-faced card using its button and F shortcut in deck, search, discovery, and recommendation canvases. The 420 ms perspective turn swaps faces at its midpoint, shades the artwork, and transforms its selection border. Quantity controls, flip controls, and labels stay in place.
- Repeated flips on one animating card are ignored; different cards can animate together. Scrolling, resizing, stack expansion, and selecting cards remain responsive. Missing destination artwork uses the standard loading/unavailable placeholder without blocking.
- Hide or close a canvas during a flip: it finishes on the intended face and clears animation state. Replace the document, undo/redo a replacement, or remove an animating card: stale animation state is discarded. Classic flip-card alternate artwork keeps its existing orientation rules.
