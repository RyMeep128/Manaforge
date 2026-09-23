# Database implementation

Callers continue to import `CardDatabase` and `default_db_path` from `mtg_core.db`.
`SCHEMA` remains available there for compatibility. Existing methods, return
values, transaction behavior, and persisted formats are unchanged by this split.

| Module | Responsibility |
| --- | --- |
| `database.py` | Public facade, connection factory, database path, repository setup |
| `schema.py` | Schema definition, creation, and existing compatibility checks |
| `cards.py` | Oracle/printing API, catalog ingestion, canonical mappings, tags, and analysis inputs |
| `catalog.py` | Transactional admin mutations and dependent-record cleanup |
| `search.py` | Local queries, FTS, structured search data, and index maintenance |
| `images.py` | Image manifests, blobs, verified asset files, and materialization |
| `preferences.py` | Artwork favorites and preference profiles |
| `sync_state.py` | Persisted synchronization checkpoints |

The facade composes internal operation groups through inheritance. These groups
are not independently instantiated repositories: they share the facade's
`db_path`, `connect()`, and transaction-maintenance methods. Keep method ownership
unique and call collaborating operations through `self`, preserving instance
overrides used by callers and tests. `CatalogRepository` receives the facade and
owns its explicit mutation transactions.

Search schema/index checks stay with search implementation; the schema group
invokes them during initialization. Formal ordered migrations remain roadmap A10.
