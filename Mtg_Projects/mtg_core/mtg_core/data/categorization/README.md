# Commander-aware categorization audit

Full offline audit executed during implementation, then rerun after reusable rule improvements. No local tests, builds, or validation suites were run; regression cases are provided for CI.

## Coverage and results

- Inventory: bundled `precons.json.gz`, installed `precons.json` when present, and every cached raw preconstructed collector response. Deduplicated by the existing catalog ID, retaining all Commander products, including sideboards and special zones. The available cached catalog and bundle contain the same 187 Commander deck identities.
- Catalog SHA-256: `2466574d4c8870d115de5fedf1db69e1a85b9242c94a6ab336692aff423cc618`.
- Original engine: rule version 7 from main commit `0ed37c47c929de7dc4495435f2c06a7b319ed051`.
- Updated engine: rule version 11.
- Decks processed in each comparable pass: 187.
- Card rows: 16,399; card copies analyzed: 18,846 / 18,846; distinct catalog card names resolved: 6,080.
- Generic type-only fallback copies: 1,028 before, 251 after (reduction 777, 75.6%). Distinct fallback names: 625 before, 200 after.
- Missing Oracle records: 0. Double-faced front names and the source catalog's `(Prepared)` suffix are normalized for lookup without changing Oracle payloads.

## Findings and changes

The initial audit exposed repeated missing goad, tribal/changeling, spell/permanent copy, equipment, extra combat, counter-doubling, team combat buff, damage prevention, control exchange, and casting-cost bypass effects. Reusable wording rules now cover these patterns. No card-name exceptions were introduced.

Commander mechanics and repeated deck payoffs seed multiple concurrent themes. Creature subtypes come from local card facts, supporting unlisted and multiple tribes. Tribal mana creatures retain Ramp as primary. Artifact/enchantment/Aura type membership joins a supported theme without creating one on its own; Treasure and other noncreature resource tokens do not alone seed a creature-token strategy. Functional evidence and deck-dependent membership remain separate.

The audit is heuristic coverage measurement, not a claim of perfect semantic accuracy. It does not force every card into a role. Remaining cases include combat-only creatures, unusual mechanics, damage amplification, hand disruption, and specialized payoffs that need further generalized rules. Highest-frequency remaining cases:

- Aethertide Whale: 3 copies
- Decoction Module: 3 copies
- Hooded Horror: 3 copies
- Master Warcraft: 3 copies
- Scythe Specter: 3 copies
- Shared Animosity: 3 copies
- Aeon Engine: 2 copies
- Armory Automaton: 2 copies
- Bitter Feud: 2 copies
- Combat Calligrapher: 2 copies
- Crashing Drawbridge: 2 copies
- Creeperhulk: 2 copies

All unresolved names and counts, each deck's commanders, supported themes/tribes, and unresolved cards are retained in `audit.json`. Baseline details are in `before/audit.json`.

## Runtime integration and regeneration

`classifications.json.gz` contains only derived effect evidence keyed by a SHA-256 fingerprint of classification-relevant facts. It contains no duplicate Oracle text, artwork, or print metadata. `role_analysis.analyze_effects` reads it once and uses entries only for the matching rule version and exact facts; new/changed cards use the same offline rules and bounded memory cache. Deck/commander context is always computed separately. The existing Manaforge build includes the entire core data directory, so the cache ships through the existing bundle infrastructure.

Editor composition/commander edits refresh automatic memberships in the existing undo transaction using cached facts. Unchanged card functions reuse memoized/generated analysis; metadata-only edits do not trigger analysis. Manual assignments, custom names, and renamed automatic categories are retained. Unused automatic categories are removed, retaining foundational Ramp, Draw, Removal, and Protection categories. Reopening a deck reevaluates automatic assignments through the existing local worker. No explanation UI was added.

From the repository root (Python with the normal application dependencies installed):

```powershell
$env:PYTHONPATH = 'Mtg_Projects/mtg_core'
python -m mtg_core.precon_audit --output Mtg_Projects/mtg_core/mtg_core/data/categorization
```

The command uses the installed card database read-only; `--database` selects another local snapshot. It bypasses the generated effect cache so future audits run the current rules. Install newer card/precon data through the existing data workflows before rerunning. Bump `RULE_VERSION` whenever effect rules change. The saved comparison uses the same catalog, Oracle lookup rules, and local data for both passes.
