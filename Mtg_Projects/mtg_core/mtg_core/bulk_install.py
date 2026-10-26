"""Bounded Scryfall import staging and transactional catalog/ruling updates."""

from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from uuid import UUID

from .db import CardDatabase
from .downloads import DownloadCancelled, check_space
from .rulings import RulingsStore, normalize_ruling


def cancelled(event):
    if event.is_set():
        raise DownloadCancelled("Paused. Completed downloads are saved for Resume.")


def records(path):
    """Read JSONL/gzip or a legacy JSON array without loading the full export."""
    path = Path(path)
    with path.open("rb") as probe:
        compressed = probe.read(2) == b"\x1f\x8b"
    with gzip.open(path, "rb") if compressed else path.open("rb") as stream:
        if stream.peek(3).startswith(b"\xef\xbb\xbf"):
            stream.read(3)
        prefix = stream.peek(4096).lstrip(b"\xef\xbb\xbf \r\n\t")
        if prefix.startswith(b"["):
            import ijson
            from ijson.common import JSONError

            try:
                yield from ijson.items(stream, "item", use_float=True)
            except JSONError as exc:
                raise ValueError("Invalid bulk JSON export") from exc
        else:
            while line := stream.readline(16 * 1024**2 + 1):
                if len(line) > 16 * 1024**2:
                    raise ValueError("A bulk record exceeds the supported size")
                if line.strip():
                    yield json.loads(line.decode("utf-8-sig"))


def _canonical(db):
    db.execute("DELETE FROM canonical_prints")
    db.execute(
        """INSERT INTO canonical_prints
        SELECT oracle_id,card_id,? FROM (
            SELECT oracle_id,card_id,row_number() OVER (PARTITION BY oracle_id ORDER BY
            coalesce(released_at,''),coalesce(set_code,''),coalesce(collector_number,''),card_id) rank
            FROM prints) WHERE rank=1""",
        (time.time(),),
    )


def _merge_table(db, table, key):
    # Both schemas are created by this application. Never execute downloaded SQL.
    columns = [r[1] for r in db.execute(f"PRAGMA main.table_info({table})")]
    updates = ",".join(f"{c}=excluded.{c}" for c in columns if c != key)
    db.execute(
        f"INSERT INTO main.{table} SELECT * FROM incoming.{table} WHERE true "
        f"ON CONFLICT({key}) DO UPDATE SET {updates}"
    )


def import_cards(path, database, version, *, cancel, report, preserve_favorites=False):
    root = Path(path).parent
    check_space(root / "stage", max(Path(path).stat().st_size * 15, 64 * 1024**2))
    with TemporaryDirectory(prefix="card-import-", dir=root) as temporary:
        staged = CardDatabase(str(Path(temporary) / "catalog.sqlite3"))
        count = 0
        with closing(staged.connect()) as db, db:
            for item in records(path):
                cancelled(cancel)
                if item.get("object") != "card" or not item.get("name"):
                    raise ValueError("Invalid Scryfall card export")
                UUID(item["id"])
                # Tokens and other supplemental cards can lack an Oracle UUID;
                # retain the service's stable synthetic identity for those.
                if item.get("oracle_id"):
                    UUID(item["oracle_id"])
                staged.upsert_card_payload(
                    item, source="scryfall-bulk", _connection=db, _refresh_state=False
                )
                staged.refresh_search_data_for_print(db, item["id"], item)
                count += 1
                if count % 500 == 0:
                    report(
                        dict(
                            operation="Preparing card catalog",
                            current=count,
                            total=None,
                            phase="initializing",
                        )
                    )
                    db.commit()
            if not count:
                raise ValueError("Scryfall returned an empty card export")
            _canonical(db)
        with closing(staged.connect()) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        cancelled(cancel)
        report(
            dict(
                operation="Applying card data and refreshing indexes",
                current=count,
                total=count,
                phase="initializing",
            )
        )
        with closing(database.connect()) as db:
            db.execute("ATTACH DATABASE ? AS incoming", (staged.db_path,))
            try:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    db.set_progress_handler(lambda: int(cancel.is_set()), 10000)
                    for table, key in (
                        ("cards_oracle", "oracle_id"),
                        ("prints", "card_id"),
                        ("print_search_data", "card_id"),
                    ):
                        _merge_table(db, table, key)
                    # Preserve preferences except a favorite whose actual Oracle
                    # identity has changed upstream; it no longer names that card.
                    if not preserve_favorites:
                        db.execute(
                            "DELETE FROM artwork_favorites WHERE EXISTS (SELECT 1 FROM prints p WHERE p.card_id=artwork_favorites.card_id AND p.oracle_id!=artwork_favorites.oracle_id)"
                        )
                    _canonical(db)
                    database.rebuild_search_index(db)
                    db.execute(
                        "INSERT OR REPLACE INTO sync_state VALUES (?,?,?,?)",
                        (
                            "installed-default_cards",
                            version,
                            time.time(),
                            json.dumps({"cards": count}),
                        ),
                    )
                    cancelled(cancel)
            except sqlite3.OperationalError:
                cancelled(cancel)
                raise
            finally:
                db.set_progress_handler(None, 0)
        return count


def import_rulings(path, service, version, *, cancel, report):
    root = Path(path).parent
    check_space(root / "stage", max(Path(path).stat().st_size * 20, 64 * 1024**2))
    with TemporaryDirectory(prefix="rulings-import-", dir=root) as temporary:
        stage = Path(temporary) / "rulings.sqlite3"
        count = 0
        with closing(sqlite3.connect(stage)) as db, db:
            db.execute("CREATE TABLE raw(oracle_id TEXT,published TEXT,payload TEXT)")
            for item in records(path):
                cancelled(cancel)
                oid, ruling = normalize_ruling(item)
                db.execute(
                    "INSERT INTO raw VALUES (?,?,?)",
                    (oid, ruling["published_at"], json.dumps(ruling)),
                )
                count += 1
                if count % 1000 == 0:
                    report(
                        dict(
                            operation="Preparing rulings",
                            current=count,
                            total=None,
                            phase="initializing",
                        )
                    )
            if not count:
                raise ValueError("Scryfall returned an empty rulings export")
            db.execute(
                "CREATE TABLE grouped AS SELECT oracle_id,json_group_array(json(payload)) payload FROM (SELECT * FROM raw ORDER BY published DESC) GROUP BY oracle_id"
            )
            db.execute("CREATE UNIQUE INDEX grouped_oracle ON grouped(oracle_id)")
        cancelled(cancel)
        store = RulingsStore(service.rulings_path)
        with closing(store.connect()) as db:
            db.execute("ATTACH DATABASE ? AS incoming", (str(stage),))
            db.execute("ATTACH DATABASE ? AS catalog", (service.database.db_path,))
            try:
                with db:
                    db.set_progress_handler(lambda: int(cancel.is_set()), 10000)
                    db.execute(
                        """INSERT OR REPLACE INTO rulings
                        SELECT c.oracle_id,?,coalesce(g.payload,'[]') FROM catalog.cards_oracle c
                        LEFT JOIN incoming.grouped g USING(oracle_id) WHERE length(c.oracle_id)=36""",
                        (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),),
                    )
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS dataset_metadata(version TEXT)"
                    )
                    db.execute("DELETE FROM dataset_metadata")
                    db.execute("INSERT INTO dataset_metadata VALUES (?)", (version,))
                    cancelled(cancel)
            except sqlite3.OperationalError:
                cancelled(cancel)
                raise
            finally:
                db.set_progress_handler(None, 0)
        return count
