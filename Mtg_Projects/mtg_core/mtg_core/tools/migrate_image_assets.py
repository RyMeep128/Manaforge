from __future__ import annotations

import argparse
from dataclasses import dataclass

from mtg_core.db import CardDatabase, default_db_path


@dataclass(frozen=True)
class MigrationResult:
    exported: int = 0
    skipped: int = 0
    failed: int = 0
    vacuumed: bool = False


def migrate_image_assets_to_files(
    database: CardDatabase,
    *,
    batch_size: int = 100,
) -> MigrationResult:
    exported = 0
    skipped = 0
    failed = 0
    blocked_asset_ids: set[str] = set()
    batch_size = max(1, int(batch_size))

    while True:
        blocked_clause = ""
        blocked_params: list[str] = []
        if blocked_asset_ids:
            placeholders = ", ".join("?" for _ in blocked_asset_ids)
            blocked_clause = f"AND asset_id NOT IN ({placeholders})"
            blocked_params = list(blocked_asset_ids)
        with database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                FROM image_assets
                WHERE length(payload) > 0
                {blocked_clause}
                ORDER BY updated_at DESC, asset_id
                LIMIT ?
                """,
                (*blocked_params, batch_size),
            ).fetchall()
            if not rows:
                break

            for row in rows:
                payload = database._row_blob(row)
                if not payload:
                    skipped += 1
                    continue
                path = database._image_asset_path(
                    row["asset_id"],
                    row["checksum"],
                    row["extension"],
                )
                try:
                    existing_path = database._resolve_image_asset_storage_path(row["storage_path"])
                    existing_payload = (
                        None
                        if existing_path is None
                        else database._read_verified_image_asset_file(existing_path, row["checksum"])
                    )
                    if existing_payload is None:
                        database._write_verified_image_asset_file(path, payload, row["checksum"])
                        storage_path = database._image_asset_storage_reference(path)
                    else:
                        storage_path = row["storage_path"]
                    connection.execute(
                        """
                        UPDATE image_assets
                        SET payload = ?,
                            payload_size = ?,
                            storage_path = ?,
                            updated_at = ?
                        WHERE asset_id = ?
                        """,
                        (
                            b"",
                            len(payload),
                            storage_path,
                            row["updated_at"],
                            row["asset_id"],
                        ),
                    )
                    exported += 1
                except OSError:
                    failed += 1
                    blocked_asset_ids.add(row["asset_id"])

    return MigrationResult(exported=exported, skipped=skipped, failed=failed)


def vacuum_database(database: CardDatabase) -> None:
    with database.connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("VACUUM")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move image asset bytes from SQLite BLOB rows to file-backed storage."
    )
    parser.add_argument(
        "--db-path",
        default=default_db_path(),
        help="SQLite DB path. Defaults to the app-data mtg_core database.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of BLOB-backed assets to export per transaction.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run SQLite VACUUM after exporting. This can take a long time on large DBs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = CardDatabase(args.db_path)
    result = migrate_image_assets_to_files(database, batch_size=args.batch_size)
    vacuumed = False
    if args.vacuum:
        vacuum_database(database)
        vacuumed = True

    print(f"Database: {database.db_path}")
    print(f"Exported: {result.exported}")
    print(f"Skipped: {result.skipped}")
    print(f"Failed: {result.failed}")
    print(f"Vacuumed: {'yes' if vacuumed else 'no'}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
