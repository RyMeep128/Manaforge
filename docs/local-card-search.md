# Local card data and search

Manaforge preserves the full Scryfall card object in each printing's `payload_json`. This includes Oracle rules text, mana cost/value, types, colors and color identity, power/toughness/loyalty, keywords, legality, flavor text, rarity, set and collector information, prices, and nested `card_faces` when supplied. The structured printing and Oracle IDs link this data to local image assets. Rules text is not inferred from an image or truncated.

Full-text search now indexes Oracle text from every face as well as names and types. Existing databases upgrade their search index automatically when opened; stored card payloads and images are retained. The initial index rebuild can take time on a large catalog. Newly imported or updated printings update the index too.

## Using local search

- **Print Proxy Prep → Add Card → Local database only** searches the stored catalog with the supported syntax below. Search and preview do not download missing artwork in this mode. Adding a result is a separate action and may need an image download.
- **Core Admin → Prints → Scryfall syntax** searches locally with the same parser, with paginated results. Disable the checkbox for the previous literal name filter. The details panel shows readable card text for all faces alongside the complete payload JSON.
- The Add Card details panel also displays the stored text. Missing local images do not prevent searching text.

Examples:

```text
t:creature c:u mv<=3
o:"draw a card" -t:land
(t:instant OR t:sorcery) id:ug
f:commander r:rare
is:dfc pow>=4
!"Sol Ring"
```

## Supported local syntax

| Syntax | Local behavior |
| --- | --- |
| `Scholar`, `"Blue Scholar"` | Card name contains the word or quoted phrase. Multiple terms are combined with AND. |
| `!"Sol Ring"`, `name=...` | Exact full card name. |
| `name:` / `n:` | Name contains text. |
| `oracle:` / `o:` | Stored Oracle text contains text, including reminder text and all faces. |
| `type:` / `t:` | Type text contains text, including all faces. |
| `flavor:` / `ft:` | Flavor text contains text, including all faces. |
| `mv`, `cmc`, `power` / `pow`, `toughness` / `tou`, `loyalty` / `loy` | Numeric comparisons with `:`, `=`, `!=`, `<`, `<=`, `>`, `>=`. Variable stats such as `*` are not treated as zero. Face stats are searched too. |
| `color:` / `c:` | Includes the requested colors; use `=` for the exact set of colors. |
| `identity:` / `id:` / `ci:` | Color identity is within the requested colors, including colorless cards. Use `=` for exact identity. |
| Color comparisons | `<`, `<=`, `>`, `>=`, `!=` compare color sets. Use WUBRG letters, individual color names, `c` / `colorless`, `m` / `multicolor`, or a color count such as `c=2`. |
| `set:` / `s:` / `e:` | Exact set code. |
| `rarity:` / `r:` | Exact rarity; `c`, `u`, `r`, `m` abbreviate common, uncommon, rare, mythic. |
| `lang:`, `layout:`, `cn:`, `artist:` | Exact stored language code, layout, collector number, or artist. |
| `legal:` / `f:` / `format:`, `banned:`, `restricted:` | Stored legality for the format; `edh` aliases `commander`. |
| `kw:` / `keyword:`, `game:` | Exact stored keyword or game entry, for example `kw:flying` or `game:paper`. |
| `is:foil`, `is:digital`, `is:reserved`, `is:reprint`, `is:promo` | Stored printing flags. |
| `is:dfc`, `is:double-faced`, `is:token` | Relevant stored layout. |
| `usd`, `eur`, `tix` | Numeric comparison of stored prices, not current market prices. |
| `AND`, `OR`, `NOT`, `-`, parentheses | Boolean combinations; AND binds more tightly than OR. Example: `-(t:creature OR t:land)`. |

Quoted values preserve spaces. `%` and `_` in text filters are literal characters, not SQL wildcards. Invalid queries and unsupported operators return an explicit error instead of falling back to a name search. Queries are parameterized, with length and nesting limits.

## Scope and data freshness

This is a documented subset of [Scryfall's search language](https://scryfall.com/docs/syntax), not a complete offline implementation of Scryfall. Oracle Tagger filters use the local Oracle Tags index. For example, `otag:ramp c=g cmc=1 legal:edh` finds one-mana, mono-green Commander-legal ramp cards. Manaforge downloads Scryfall's Oracle Tags bulk file on the first `otag:` search and stores it locally. The database Sync tab also provides **Update Oracle Tags** for an explicit refresh. Regular expressions, illustration tags (`atag:`), mana-symbol expressions, most special `is:` predicates, and result directives such as `unique:` and `order:` require online search. Add Card returns one canonical printing per Oracle card and retrieves one 250-result page plus a single lookahead result instead of loading every match.

Only records already in the catalog can match. Imported images or manually created records without rules text cannot match a rules-text query until complete card data is supplied. Existing catalog downloads/imports retain full card payloads; updating a printing updates its searchable text. Legality, prices, and Oracle text reflect the last stored payload. The local Add Card catalog excludes the temporary online-search cache; Core Admin can inspect those cached records as well.

For callers of the shared service:

```python
results = service.search_cards(
    't:creature o:"draw a card" mv<=3',
    {"scryfall_syntax": True, "allow_remote": False, "online_mode": False},
)
```

Ordinary `search_prints()` also searches the full-text index (names, types, and rules); use syntax mode when unprefixed words should only match names.
