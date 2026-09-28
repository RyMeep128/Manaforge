# Card service internals

Applications continue to import `CardService` and `get_default_card_service`
from `mtg_core.services`. The facade owns the database, image root, injected
network functions, printing-refresh cache, and default-service lifecycle.

Internal operation groups follow the same pattern as `CardDatabase`:

| Module | Responsibility |
| --- | --- |
| `search.py` | Local/remote search, card and printing lookup, editor analysis reads |
| `artwork.py` | Artwork favorites, preference profiles, preferred-print selection |
| `images.py` | Image lookup, download, asset storage/materialization, local validation |
| `catalog_sync.py` | Bulk catalog and Oracle-tag sync, resumable download state |
| `constants.py` | Existing persistent sync identifiers and defaults |

Instantiate the facade, not the operation groups. All groups share the same
instance and call other operations through `self`; subclass overrides and
replacement fetch functions therefore remain effective across groups. Modules
do not import the facade or own additional database connections or lifecycle
state. Public sync constants and `RemoteLookupUnavailable` remain available at
the package boundary for existing callers.

This is an internal organization change, with no schema, serialized-state, or
user-interface changes. Core and integration tests cover search cancellation,
artwork precedence, image reuse, and resumable synchronization; boundary tests
also exercise overrides and replaced dependencies across operation groups.
