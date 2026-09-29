# Database implementation

Callers continue to import `CardDatabase` and `default_db_path` from `mtg_core.db`.
`SCHEMA` remains available there for compatibility. Existing methods, return
values, transaction behavior, and persisted formats are unchanged by this split.

| Module | Responsibility |
| --- | --- |
| `database.py` | Public facade, connection factory, database path, repository setup |
| `schema.py` | Versioned schema, ordered transactional migrations, and startup checks |
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
invokes them during initialization, including repair of derived indexes on current
databases. SQLite `PRAGMA user_version` records the schema version. Version zero
covers empty and historical unversioned databases; migration 1 creates missing
tables, adds compatibility columns, and then creates dependent indexes without
replacing user tables or artwork.

Startup holds an immediate transaction while reading the version and applying
ordered migrations. Schema changes and version updates roll back together on
failure. Newer versions are rejected before schema changes. Connections close
after initialization, including failed upgrades.

For future changes, append a migration method name to `MIGRATIONS` and increment
`SCHEMA_VERSION`; retain the version-1 baseline and prior migration order. Use
`connection.execute`, not `executescript` or explicit commits, inside migrations
to preserve the enclosing transaction. Add upgrade and rollback coverage for CI.
