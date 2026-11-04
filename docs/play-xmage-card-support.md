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

## Repeatable complete inventory

Use GitHub Actions for all test suites; do not run the historical local test commands.
The `XMage coverage audit regression` workflow covers classification, Oracle/set
counting, identity, upstream evidence, decks, and deterministic report serialization.

```powershell
git -C C:/Users/ryanm/Source/Manaforge-XMage fetch upstream master
python tools/build_xmage_backlog.py --audit --source C:/Users/ryanm/Source/Manaforge-XMage --upstream upstream/master --output Artifacts/XmageCoverageAudit-NEW
```

This extends the existing backlog tool and uses the same installed-catalog probe,
identity resolver, class comparison, and upstream registration index. It does not
require Forge. `--catalog`, `--server-dir`, and `--saved-decks` select explicit
inputs. Output destinations must be new directories. Missing inputs fail; an old
report is never substituted. `Artifacts/` is ignored by Git.

`audit.json` contains all Oracle identities, statuses, sets, Scryfall legality and
classification evidence, upstream source references, deck results, input warnings,
and provenance. Sortable CSVs include `cards`, `missing`, `commander-missing`,
`novelty-missing`, `sets`, `decks`, `upstream-missing`, `backlog`, and
`dependency-candidates`. `summary.md` contains every affected ordinary-paper set,
the complete missing Commander list, counts, and saved-deck compatibility.

Global totals count each Oracle ID once. Within a set, variants/printings of an
Oracle card count once. Reprints count separately in each set: do not sum set
counts to get the global count. Set eligibility follows printing classification;
an art-series printing does not make an ordinary card eligible in an art set.
Cards present only in `cards_oracle` without prints are unresolved, not paper.

Classification considers all printings. A normal paper printing takes precedence
over a silver, digital, or non-game reprint of the same Oracle card. Acorn stamps,
silver borders and playtest markers identify novelty; `set_type=funny` alone
does not. A funny-set object with known legalities all `not_legal` and no ordinary
printing is novelty. Commander counts require Scryfall `commander=legal`, not
merely a black border. Missing/contradictory legality evidence is retained.
Variant objects (planes, schemes, conspiracies, vanguards, stickers), art objects,
tokens/emblems, and digital-only objects remain separate. Ordinary-paper counts
include preview cards; release dates and a future-only missing count are reported.
Legality reflects the installed Scryfall snapshot, not a fresh online ruling.

Sources: [Wizards Unfinity release notes](https://magic.wizards.com/en/news/feature/unfinity-release-notes-2022-10-07)
and [Scryfall card fields](https://github.com/scryfall/api-types/blob/main/src/objects/Card/CardFields.ts).

An available class is **not verified rules behavior**. Audit mode conservatively
marks all behavior unverified; the legacy backlog's optional matching JUnit/engine
lock association remains available for focused behavioral evidence. Upstream
means an uncommented registration and corresponding Java source at the recorded
revision; it is an update candidate, not compiled/runtime/behavior verification.
No upstream evidence means none found by that index, not proof of impossibility.
Multi-face unresolved identities remain explicit review items; there is no guessed
front-face substitution. Installed missing-card, missing-class and identity statuses
remain intact even when upstream source exists.

Deck totals deduplicate positive-quantity mainboard, commander and sideboard
entries by canonical Oracle ID (exact normalized name only when no ID exists).
Generated token/emblem entries and display copies are reported separately. Token
dependency counts describe unresolved catalog evidence; generated token correctness
requires engine-level investigation and is not inferred from missing card records.
Identity-review counts are not confirmed absent implementations.
Rules availability does not certify a legal deck or successful launch: format,
quantities and engine validation are not executed by this read-only audit.
Saved files are hashed before/after and never rewritten. Existing locally cached
shared deck snapshots are included through the application's discovery API.

Backlog priority is saved-deck blockers, Commander cards with upstream evidence,
other Commander cards, other paper cards, then optional objects. Shared keyword
groups identify candidates for mechanic investigation; they do not assert the
engine lacks that mechanic. There are no invented effort or popularity scores.

Historical counts formerly in this document are superseded by newly generated
snapshot reports; do not use them as current coverage evidence.

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
