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
