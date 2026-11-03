# Checking installed XMage card coverage

Run from the repository root with Python and the installed Java 11+ JDK:

```powershell
# All saved Manaforge decks, checking card rules availability regardless of deck printing
python tools/check_xmage_cards.py

# All unique card names in the installed local Core catalog
python tools/check_xmage_cards.py --all-cards --output Artifacts/XmageCardSupport-AllCards

# A particular native saved deck or exact card name
python tools/check_xmage_cards.py --deck "C:/path/to/deck.manaforge.json"
python tools/check_xmage_cards.py --name "Feather, Radiant Arbiter"
```

Reports contain `report.json`, `summary.txt`, `available.csv`, `missing.csv`,
`invalid.csv`, and `skipped.csv`. CSVs open in Excel; JSON preserves literal
names. Counts represent entry rows, not summed deck quantities.

The checker reads the existing H2 server catalog directly in read-only mode and
checks its recorded implementation class names against installed JAR entries.
It selects a completed local server whose mage-sets JAR matches the installed
bundle. Use `--server-dir` to select an initialized server explicitly, `--java`
for a JDK executable, or `--catalog-db` with `--all-cards` for another Core SQLite
catalog. If no initialized server exists, launch and close a normal Play session
first. It never downloads data, starts XMage, initializes databases, modifies decks,
or substitutes card printings. Source database and engine hashes are recorded.

## Interpreting results

- `available`: card name and an implementation class found in XMage, regardless of the deck's selected set or collector number.
- `missing_card`: no exact card-name record in this installed XMage catalog.
- `missing_implementation`: the catalog record exists, but its recorded class is absent.
- `invalid_metadata`: no usable name.
- `skipped`: display commanders, considering/excluded entries, and zero quantities.

This is catalog coverage, not proof of rules correctness or legal deck construction.
Names are exact: aliases and combined double-face names are not guessed. Full
Core catalogs also include tokens, novelty objects, and nonstandard cards. Some
split-card half records refer to synthetic class names; a missing recorded class
for a half does not prove the complete split card is unsupported. Inspect the
complete card before treating such findings as missing rules implementations.

Exit codes: 0 means the comparison completed, 2 means a configuration/read error.
Add `--fail-on-missing` to return 1 for any non-skipped card support issue.

## Focused verification

```powershell
python -m pytest Mtg_Projects/mtg_play/tests/test_xmage_support.py -q
python -m ruff check Mtg_Projects/mtg_play/xmage_support.py Mtg_Projects/mtg_play/tests/test_xmage_support.py tools/check_xmage_cards.py
```

Verified against the installed catalog: Blame Game has 86 available entry rows,
two missing exact card names (Feather, Radiant Arbiter; Immortal Obligation),
and one skipped display commander. The full local Core comparison reports
31,347 names with recorded classes, 7,486 names without exact catalog records,
and four split-half records with absent recorded classes. These numbers describe
this local snapshot and will change as catalogs and XMage builds change.

Deck printing metadata is retained only as provenance in reports. It never affects
classification. The live launcher also resolves rules by card name, independent of deck printing.
It validates the resolved engine deck and sends the resolved set/number to XMage.
The private runtime manifest retains the original card_id/oracle_id for artwork;
the saved deck is never rewritten. Verified double-face names use the existing
XMage face-name matching. Missing rules still fail before game startup.

## Rules coverage report correction

The current checker normalizes case and apostrophe variants and follows explicit
XMage face relationships. It also writes plain `cards-not-in-xmage.txt` and
`cards-in-xmage.txt` lists. The latest local full-catalog report is in
`Artifacts/XmageRulesCoverage`: 32,066 available names, 6,767 names absent from
the installed catalog, and four unresolved split-half class records. This replaces
the older exact-name counts above. The absent list includes nonstandard objects
and tokens from Core; it is not a count of ordinary tournament cards alone.
