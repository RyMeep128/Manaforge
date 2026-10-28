# Automatic card categorization

The primary category describes the card's job. Deck strategy membership is
secondary evidence, not a competing job. An enchantment can provide ramp, draw,
protection, or interaction while also belonging to an enchantment strategy.

`categorization_policy.py` orders evidence in explicit layers:

1. Commander/land designations.
2. Functional effects supported by the card's rules.
3. Local role tags without a matching parsed effect.
4. Supporting themes, whether inferred from the card or the deck.
5. Incidental abilities, such as self-resilience and self-casting keywords.
6. Card-type fallbacks when no role evidence exists.

Numeric scores compare evidence within a layer. Commander support, repeated deck
mechanics, and explicit theme preferences cannot promote a theme over a supported
function. Merely creating a category cannot siphon functional cards into it.
Existing custom names and renamed automatic IDs are reused when applying the
selected role. Explicit card-level manual assignments remain protected. When no
supported function exists, the previous custom-category preference for keyword
roles remains available rather than discarding user organization.

All secondary roles remain available for search, filtering, and deck analysis.
The classifier, deck refresh, initial hydration, and category application use the
same evidence policy. Stored evidence includes its layer; old unlayered provider
evidence remains readable using the legacy ordering behavior.

Functional parsing still requires conservative wording rules. Recent additions
cover grants of protection and evasion, draw-step card access, land untapping, and
graveyard targeting restrictions. These are Oracle-effect patterns, never card-name
exceptions. Unsupported or ambiguous wording can still require a manual category.

CI regressions include a type/function/context/category matrix, the existing Oracle
fixture corpus, recipient-scope negative cases, stable reapplication, and the nine
reported examples. They test primary-role precedence rather than only counting
how many cards receive any category. A reduction in uncategorized cards alone is
not evidence that the chosen roles are correct.

Rule version 13 invalidates older generated effect snapshots. The existing
version-12 precon audit and generated data are historical measurements; runtime
uses current memoized rules when the bundled version does not match. Regenerate
with the existing precon audit command during the next approved dataset refresh;
do not relabel old measurements as results for the new policy.

## Community manual evidence

Category provenance lives in each entry's `extras.auto_categories`. Engine choices
have `origin: automatic`. Deliberate radial/menu/drag choices have `origin: manual`,
`manual: true`, and `manual_ids` for memberships the player actually selected.
Changing a secondary membership does not verify an untouched automatic primary.
Legacy unknown assignments remain protected and are never contributed. Recognizable
older generated records remain automatic. Imports discard category provenance.

The existing Libraries menu has a default-off **Share manual categories when
publishing decks** setting for each library. Publishing batches eligible choices
for that snapshot through the existing retry journal. No private local decks are
scanned or uploaded. Evidence contains supported category names, exact Oracle IDs,
primary functional labels, and explicit strategy keys. Existing publication
permissions still govern sharing the deck itself.

The optional `manual_category_evidence_v1` capability adds an authenticated compact
feed and owner-only replacement batches. Servers bind batches to the current
published revision and reject cards absent from it. Downloads carry library-scoped
pseudonymous contributor keys and deck fingerprints for deduplication, omitting
usernames, deck names, decklists, notes and local IDs. Clients attest deliberate
input; the protocol cannot prove human input or identify the same person across
independent servers/accounts. This is supporting evidence, not a reputation system.

Refresh runs on connection and during existing background library browsing, at most
once per 24 hours per server, including failed attempts. **Refresh community
categories** bypasses the interval. Pages are staged and swapped atomically;
unchanged snapshot hashes avoid repeated downloads. Changed snapshots replace the
compact cache, reflecting unpublication and permission changes. Older servers are
skipped. Network/storage failures retain local knowledge; access rejection clears
the library's records. Signing out, removing a connection or switching accounts
clears local evidence and contribution consent. Offline caches otherwise remain
until the next successful refresh. Turning contributions off stops future uploads,
including pending retries. Previously shared evidence remains tied to its published
revision; publishing a newer revision or unpublishing removes it from the feed.

Scoring reads exact-card records in one indexed local batch, with no lock wait or
transport. Missing, locked or damaged caches fall back to the existing engine.
Evidence must match format and either commander pairing or an explicit theme.
Each author and deck fingerprint contributes at most once; conflicting copies
abstain. At least three independent supporting contributors and 75% weighted
agreement are required. Commander matches weigh more than theme matches. Available
primary-function labels must agree with a detected function. An accepted signal
adds four points to an already-detected role within three points of the leading
role, inside the same priority layer. It cannot invent a specialized role or
promote a theme over a function. Correct generic fallbacks are retained.

The shared apply path also uses explicit themes and typal subtypes for supported
strategy memberships. Commander/theme changes reevaluate automatic entries and
preserve manual and unknown player choices. The legacy reconsider argument remains
accepted but cannot overwrite manual choices. Downloads never traverse decks or
trigger recategorization. No activity or timing analytics are collected.

## Independent evaluation

`categorization_evaluation.evaluate` compares labelled DeckDocuments with an empty
community snapshot and a supplied local snapshot through the actual apply/refresh
engine. Labels specify acceptable primary roles and functional/contextual groups.
Reports include primary accuracy, incorrect specializations, generic fallbacks,
manual preservation, strategy breakdowns and local execution time. Generic choices
count as correct only when labelled acceptable. Timings are development measurements,
never telemetry.

Existing CI runs provenance, permissions, sparse/contradictory evidence, offline,
manual-preservation and paired classification regressions. It uploads paired metrics
for small authored strategy samples covering Tribal, Aristocrats, Tokens,
Enchantments, Artifacts, Spellslinger, Landfall, Voltron, Graveyard and Mixed decks.
The community fixture deliberately contradicts primary functions; separate tie
regressions verify useful refinement. These samples are not representative full
player decks and do not establish the aspirational 90–98% target. A consented,
independently reviewed full-deck holdout corpus is still needed before reporting
production accuracy. Precon development data is excluded from this evaluation.


Rule version 14 treats tag-only evasion as incidental. Functional grants of evasion
remain functional evidence. Card access now recognizes bounded multi-sentence
reveals and pile selection, casting from inspected hands or revealed/exiled library
cards, cascade, and manifest. Looking at the library without gaining a card remains
Utility. These rules use effect wording and recipient scope, never card names;
old generated snapshots fall back to the current memoized rules.
