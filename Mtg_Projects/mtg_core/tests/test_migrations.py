import sqlite3

import pytest

from mtg_core.db import CardDatabase
from mtg_core.db import schema


def legacy_database(path):
    sql = schema.SCHEMA
    for column in (
        "    asset_id TEXT,\n",
        "    cache_scope TEXT,\n",
        "    cache_expires_at REAL,\n",
        "    payload_size INTEGER,\n",
        "    storage_path TEXT,\n",
    ):
        sql = sql.replace(column, "")
    sql = sql.replace(
        "CREATE INDEX IF NOT EXISTS idx_prints_online_cache ON prints(cache_scope, cache_expires_at);",
        "",
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO artwork_preference_profiles VALUES ('saved', '{}', 1)"
        )
        connection.execute(
            "INSERT INTO cards_oracle VALUES ('oracle', 'Card', 'card', 'normal')"
        )
        connection.execute(
            "INSERT INTO prints (card_id, oracle_id, name, payload_json, updated_at) "
            "VALUES ('print', 'oracle', 'Card', ?, 1)",
            ('{"id":"print","oracle_id":"oracle","name":"Card"}',),
        )
        connection.execute(
            "INSERT INTO image_assets (asset_id, checksum, payload, created_at, updated_at) "
            "VALUES ('art', 'checksum', ?, 1, 1)",
            (b"owned-image",),
        )


@pytest.mark.parametrize("legacy", [False, True])
def test_create_or_upgrade_and_reopen_without_rerunning_migration(tmp_path, legacy):
    path = str(tmp_path / "cards.sqlite3")
    if legacy:
        legacy_database(path)
    database = CardDatabase(path)
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == schema.SCHEMA_VERSION
        )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(prints)")
        }
        assert {"cache_scope", "cache_expires_at"} <= columns
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='idx_prints_online_cache'"
        ).fetchone()
        if legacy:
            assert (
                connection.execute("SELECT payload FROM image_assets").fetchone()[0]
                == b"owned-image"
            )
            assert (
                connection.execute(
                    "SELECT profile_key FROM artwork_preference_profiles"
                ).fetchone()[0]
                == "saved"
            )
            assert (
                connection.execute("SELECT card_id FROM print_search_data").fetchone()[
                    0
                ]
                == "print"
            )

    class Reopened(CardDatabase):
        def _migrate_to_v1(self, connection):
            raise AssertionError("Current databases must not rerun migrations")

    Reopened(path)


@pytest.mark.parametrize("fail_after_version", [False, True])
def test_failed_upgrade_rolls_back_columns_and_version_then_retries(
    tmp_path, fail_after_version
):
    path = str(tmp_path / "cards.sqlite3")
    legacy_database(path)

    class Failing(CardDatabase):
        def _migrate_to_v1(self, connection):
            super()._migrate_to_v1(connection)
            if not fail_after_version:
                raise RuntimeError("interrupted upgrade")

        def _ensure_search_data(self, connection):
            super()._ensure_search_data(connection)
            raise RuntimeError("interrupted upgrade")

    with pytest.raises(RuntimeError, match="interrupted upgrade"):
        Failing(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "cache_scope" not in {
            row[1] for row in connection.execute("PRAGMA table_info(prints)")
        }
        assert (
            connection.execute("SELECT payload FROM image_assets").fetchone()[0]
            == b"owned-image"
        )
    CardDatabase(path)


def test_future_schema_is_rejected_without_creating_tables(tmp_path):
    path = str(tmp_path / "future.sqlite3")
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 1}")
    with pytest.raises(ValueError, match="newer than supported"):
        CardDatabase(path)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == schema.SCHEMA_VERSION + 1
        )
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_migrations_run_in_order_and_advance_version(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(schema, "MIGRATIONS", (*schema.MIGRATIONS, "_migrate_to_v2"))

    class NextVersion(CardDatabase):
        def _migrate_to_v2(self, connection):
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
            connection.execute("CREATE TABLE migration_two (value TEXT)")

    database = NextVersion(str(tmp_path / "cards.sqlite3"))
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT * FROM migration_two").fetchall() == []
