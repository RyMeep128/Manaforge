# Strategic categorization fixtures

`lyra_reference.txt` preserves the supplied deck list verbatim. Its quantities
sum to 110 (77 distinct entries), not the 100 stated in the story. Parsed counts
include Land 36, Draw 11, and Protection 9. Expectations are per entry, including
34 Plains and the explicitly designated commander.

`lyra_oracle.json` and `strategy_oracle.json` contain card inputs retrieved from
the [Scryfall collection API](https://scryfall.com/docs/api/cards/collection).
They retain only identification and classification metadata, without images.
Snapshot printing IDs can differ from the list's set codes: these fixtures test
Oracle functionality, not printing resolution. CI reads these committed files
without any network access. Production classification continues using the local
database and saved card facts.

To refresh Oracle inputs, submit the fixture card names to the collection API in
batches of at most 75 identifiers, preserve the existing classification fields,
and review any wording changes before replacing snapshots. Do not change an
expected role solely to match current classifier output.

The classifier recognizes bounded wording patterns and explicit keywords; it is
not a complete rules interpreter. Novel wording, unusual replacement effects,
and combos whose meaning emerges only across several cards may need manual
categories. Commander/theme bonuses break close strategic choices, not strong
functional priorities.
