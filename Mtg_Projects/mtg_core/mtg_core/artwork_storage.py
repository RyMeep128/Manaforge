"""Resumable inventory and reviewed, path-preserving artwork deduplication.

The journal is separate from the card catalog. Only checksum-verified Scryfall
manifest paths can become cleanup candidates; unidentified files are inventory only.
"""

from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from .artwork_storage_lock import cancelled, storage_lock


def signature(info):
    return json.dumps(
        [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink]
    )


def safe_path(path, root):
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    if not path.is_relative_to(root):
        raise ValueError("Path is outside the managed artwork directory")
    for part in (path, *path.parents):
        if part.is_symlink() or (
            hasattr(os.path, "isjunction") and os.path.isjunction(part)
        ):
            raise ValueError("Linked directories and symbolic links are excluded")
    return path


def digest(path, cancel):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            cancelled(cancel)
            value.update(block)
    return value.hexdigest()


class ArtworkStorage:
    def __init__(self, database, root, journal=None):
        self.database = database
        # A user-selected root may itself be a legacy directory junction. Resolve
        # that boundary once; links *inside* the managed folders remain excluded.
        resolved = Path(root).resolve()
        if not str(root).strip() or not resolved.is_dir():
            raise ValueError("Choose an existing artwork folder")
        self.root = safe_path(resolved, resolved)
        self._root_aliases = {}
        self.cache = self.root / "mtg_core_cache"
        self.assets = self.root / "assets"
        identity = hashlib.sha256(
            (str(Path(database.db_path).resolve()) + str(self.root)).encode()
        ).hexdigest()[:20]
        self.journal = (
            Path(journal)
            if journal
            else Path(database.db_path).parent / f"artwork-audit-{identity}.sqlite3"
        )

    def _physical(self, path, kind):
        path = Path(os.path.abspath(path))
        if path.is_relative_to(self.root):
            return path
        for parent in path.parents:
            if parent.name == kind:
                boundary = parent.parent
                key = str(boundary)
                if key not in self._root_aliases:
                    self._root_aliases[key] = boundary.resolve()
                if self._root_aliases[key] == self.root:
                    return self.root / path.relative_to(boundary)
                break
        return path

    def connect(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.journal, timeout=30)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY, signature TEXT, device TEXT, inode TEXT,
                bytes INTEGER, links INTEGER, checksum TEXT, seen TEXT,
                role TEXT DEFAULT 'unknown');
            CREATE TABLE IF NOT EXISTS pairs (
                path TEXT PRIMARY KEY, canonical TEXT, checksum TEXT,
                status TEXT, detail TEXT, temporary TEXT, bytes INTEGER DEFAULT 0,
                manifest_path TEXT);
            CREATE TABLE IF NOT EXISTS issues (path TEXT PRIMARY KEY, detail TEXT);
        """)
        binding = json.dumps(
            [str(Path(self.database.db_path).resolve()), str(self.root)]
        )
        old = db.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
        if old and old[0] != binding:
            db.close()
            raise ValueError("Audit belongs to a different catalog or artwork folder")
        columns = {
            row["name"]: row["type"] for row in db.execute("PRAGMA table_info(files)")
        }
        if columns["device"].upper() != "TEXT":
            # Windows volume IDs are unsigned 64-bit values. INTEGER affinity can
            # also coerce decimal strings to lossy REALs, so change the column type.
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DROP TABLE IF EXISTS files_device_text")
                db.execute("""CREATE TABLE files_device_text (
                    path TEXT PRIMARY KEY, signature TEXT, device TEXT, inode TEXT,
                    bytes INTEGER, links INTEGER, checksum TEXT, seen TEXT,
                    role TEXT DEFAULT 'unknown')""")
                db.execute("""INSERT INTO files_device_text
                    SELECT path,signature,CAST(device AS TEXT),inode,bytes,links,
                           checksum,seen,role FROM files""")
                db.execute("DROP TABLE files")
                db.execute("ALTER TABLE files_device_text RENAME TO files")
        db.execute("INSERT OR IGNORE INTO meta VALUES ('binding', ?)", (binding,))
        db.commit()
        return db

    def _issue(self, db, path, detail):
        db.execute(
            "INSERT OR REPLACE INTO issues VALUES (?, ?)", (str(path), str(detail))
        )

    def _inventory(self, db, cancel, report):
        generation = uuid.uuid4().hex
        count = 0
        last_report = 0
        for root in (self.assets, self.cache):
            if not root.exists():
                self._issue(db, root, "Managed directory is missing")
                continue

            def visit_error(error):
                self._issue(db, error.filename or root, error)

            for folder, dirs, files in os.walk(
                root, followlinks=False, onerror=visit_error
            ):
                cancelled(cancel)
                allowed = []
                for name in dirs:
                    try:
                        safe_path(Path(folder) / name, root)
                        allowed.append(name)
                    except (OSError, ValueError) as exc:
                        self._issue(db, Path(folder) / name, exc)
                dirs[:] = allowed
                for name in files:
                    cancelled(cancel)
                    path = Path(folder) / name
                    try:
                        safe_path(path, root)
                        info = path.stat()
                        if not stat.S_ISREG(info.st_mode):
                            raise ValueError("Not a regular file")
                        stamp = signature(info)
                        old = db.execute(
                            "SELECT signature,checksum FROM files WHERE path=?",
                            (str(path),),
                        ).fetchone()
                        cached_hash = old[1] if old and old[0] == stamp else None
                        db.execute(
                            "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,'unknown')",
                            (
                                str(path),
                                stamp,
                                str(info.st_dev),
                                str(info.st_ino),
                                info.st_size,
                                info.st_nlink,
                                cached_hash,
                                generation,
                            ),
                        )
                    except (OSError, ValueError) as exc:
                        self._issue(db, path, exc)
                    count += 1
                    if time.monotonic() - last_report > 0.25:
                        db.commit()
                        report(
                            dict(
                                operation="Inventorying artwork files",
                                current=count,
                                total=None,
                                phase="artwork-audit",
                            )
                        )
                        last_report = time.monotonic()
        db.execute("DELETE FROM files WHERE seen != ?", (generation,))
        db.commit()

    def _verified(self, db, path, expected, root, cancel, *, fresh=False):
        safe_path(path, root)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Not a regular artwork file")
        stamp = signature(before)
        row = db.execute(
            "SELECT signature,checksum FROM files WHERE path=?", (str(path),)
        ).fetchone()
        actual = row[1] if row and row[0] == stamp and not fresh else None
        if actual is None:
            actual = digest(path, cancel)
        if signature(path.stat()) != stamp:
            raise ValueError("File changed during verification")
        if actual != expected:
            raise ValueError("Checksum mismatch; file was preserved")
        db.execute(
            "UPDATE files SET signature=?,checksum=? WHERE path=?",
            (stamp, actual, str(path)),
        )
        return before

    def audit(self, *, cancel, report):
        with (
            storage_lock(self.root / ".artwork-audit-session", cancel),
            closing(self.connect()) as db,
        ):
            db.execute("INSERT OR REPLACE INTO meta VALUES ('complete','false')")
            db.execute("DELETE FROM issues")
            db.commit()
            self._recover(db)
            self._inventory(db, cancel, report)
            # Rebuild candidate classifications; immutable file hashes survive a resume.
            db.execute("DELETE FROM pairs")
            with closing(self.database.connect()) as catalog:
                assets = catalog.execute(
                    "SELECT storage_path,checksum,source FROM image_assets"
                ).fetchall()
                rows = catalog.execute("""
                    SELECT m.path,a.storage_path,a.checksum,m.checksum,m.source,a.source
                    FROM image_manifest m JOIN image_assets a ON a.asset_id=m.asset_id
                    WHERE m.path IS NOT NULL
                """).fetchall()
            for index, asset in enumerate(assets):
                cancelled(cancel)
                path = self.database._resolve_image_asset_storage_path(asset[0])
                if path is None:
                    continue
                path = self._physical(path, "assets")
                if not path.is_relative_to(self.assets):
                    continue
                db.execute(
                    "UPDATE files SET role='canonical' WHERE path=?", (str(path),)
                )
                try:
                    with storage_lock(self.root, cancel):
                        self._verified(db, path, asset[1], self.assets, cancel)
                except (OSError, ValueError) as exc:
                    self._issue(db, path, exc)
                db.commit()
                report(
                    dict(
                        operation="Verifying canonical artwork",
                        current=index + 1,
                        total=len(assets),
                        phase="artwork-audit",
                    )
                )
            conflicts = Counter(
                str(self._physical(row[0], "mtg_core_cache")) for row in rows
            )
            total = len(rows)
            for index, row in enumerate(rows):
                cancelled(cancel)
                path = self._physical(row[0], "mtg_core_cache")
                canonical = self.database._resolve_image_asset_storage_path(row[1])
                if not path.is_relative_to(self.cache):
                    continue
                db.execute("UPDATE files SET role='legacy' WHERE path=?", (str(path),))
                status, detail = "preserved", "Custom, ambiguous, or unmanaged artwork"
                size = 0
                try:
                    if (
                        row[4] != "scryfall"
                        or row[5] != "scryfall"
                        or conflicts[str(path)] != 1
                    ):
                        raise ValueError(detail)
                    if not canonical or not row[2] or (row[3] and row[3] != row[2]):
                        raise ValueError("Missing or conflicting canonical checksum")
                    canonical = self._physical(canonical, "assets")
                    with storage_lock(self.root, cancel):
                        a = self._verified(db, path, row[2], self.cache, cancel)
                        b = self._verified(db, canonical, row[2], self.assets, cancel)
                        size = a.st_size
                        if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                            status, detail = (
                                "linked",
                                "Already shares canonical storage",
                            )
                        elif a.st_dev != b.st_dev:
                            raise ValueError("Different volumes; cannot hard link")
                        elif a.st_nlink != 1:
                            raise ValueError(
                                "Other hard links exist; savings cannot be guaranteed"
                            )
                        else:
                            status, detail = (
                                "duplicate",
                                "Both files match the canonical checksum",
                            )
                except (OSError, ValueError) as exc:
                    detail = str(exc)
                    self._issue(db, path, detail)
                db.execute(
                    "INSERT OR REPLACE INTO pairs VALUES (?,?,?,?,?,NULL,?,?)",
                    (
                        str(path),
                        str(canonical) if canonical else "",
                        row[2],
                        status,
                        detail,
                        size,
                        row[0],
                    ),
                )
                db.commit()
                report(
                    dict(
                        operation="Verifying artwork duplicates",
                        current=index + 1,
                        total=total,
                        phase="artwork-audit",
                    )
                )
            db.execute("INSERT OR REPLACE INTO meta VALUES ('complete','true')")
            db.commit()
            return self._summary(db)

    def _recover(self, db):
        for row in db.execute("SELECT * FROM pairs WHERE status='prepared'").fetchall():
            path, canonical = Path(row["path"]), Path(row["canonical"])
            try:
                safe_path(path, self.cache)
                safe_path(canonical, self.assets)
                linked = (
                    path.is_file()
                    and canonical.is_file()
                    and os.path.samefile(path, canonical)
                )
                # Only the exact journaled, generated temporary hard link is ours.
                temporary = Path(row["temporary"]) if row["temporary"] else None
                if (
                    temporary
                    and temporary.parent == path.parent
                    and temporary.name.startswith(path.name + ".dedup-")
                ):
                    safe_path(temporary, self.cache)
                    if (
                        temporary.is_file()
                        and canonical.is_file()
                        and os.path.samefile(temporary, canonical)
                    ):
                        temporary.unlink()
                db.execute(
                    "UPDATE pairs SET status=?,temporary=NULL,detail=? WHERE path=?",
                    (
                        "linked" if linked else "duplicate",
                        "Recovered interrupted operation",
                        str(path),
                    ),
                )
            except (OSError, ValueError) as exc:
                self._issue(db, path, exc)
        db.commit()

    def reclaim(self, *, cancel, report):
        with (
            storage_lock(self.root / ".artwork-audit-session", cancel),
            closing(self.connect()) as db,
        ):
            complete = db.execute(
                "SELECT value FROM meta WHERE key='complete'"
            ).fetchone()
            if not complete or complete[0] != "true":
                raise ValueError(
                    "Complete and review an artwork audit before reclaiming space"
                )
            self._recover(db)
            rows = db.execute("SELECT * FROM pairs WHERE status='duplicate'").fetchall()
            reclaimed = 0
            linked = 0
            for index, row in enumerate(rows):
                cancelled(cancel)
                path, canonical = Path(row["path"]), Path(row["canonical"])
                temporary = path.with_name(path.name + ".dedup-" + uuid.uuid4().hex)
                try:
                    with storage_lock(self.root, cancel):
                        with closing(self.database.connect()) as catalog:
                            mappings = catalog.execute(
                                """
                                SELECT a.storage_path,a.checksum,m.checksum,m.source,a.source
                                FROM image_manifest m JOIN image_assets a ON a.asset_id=m.asset_id
                                WHERE m.path=?
                            """,
                                (row["manifest_path"],),
                            ).fetchall()
                        if len(mappings) != 1:
                            raise ValueError("Artwork mapping changed since review")
                        mapping = mappings[0]
                        mapped_path = self.database._resolve_image_asset_storage_path(
                            mapping[0]
                        )
                        if (
                            mapping[3] != "scryfall"
                            or mapping[4] != "scryfall"
                            or mapping[1] != row["checksum"]
                            or (mapping[2] and mapping[2] != row["checksum"])
                            or mapped_path is None
                            or self._physical(mapped_path, "assets") != canonical
                        ):
                            raise ValueError(
                                "Artwork ownership or canonical mapping changed since review"
                            )
                        # Never trust an old review: re-read both files before replacement.
                        a = self._verified(
                            db, path, row["checksum"], self.cache, cancel, fresh=True
                        )
                        b = self._verified(
                            db,
                            canonical,
                            row["checksum"],
                            self.assets,
                            cancel,
                            fresh=True,
                        )
                        if os.path.samefile(path, canonical):
                            db.execute(
                                "UPDATE pairs SET status='linked' WHERE path=?",
                                (str(path),),
                            )
                            db.commit()
                            continue
                        if a.st_dev != b.st_dev or a.st_nlink != 1:
                            raise ValueError(
                                "File links or volume changed since review"
                            )
                        db.execute(
                            "UPDATE pairs SET status='prepared',temporary=? WHERE path=?",
                            (str(temporary), str(path)),
                        )
                        db.commit()  # Durable intent before touching the duplicate.
                        os.link(canonical, temporary)
                        # Creating our link increments canonical nlink, so compare its other fields.
                        latest = canonical.stat()
                        if signature(path.stat()) != signature(a) or (
                            latest.st_dev,
                            latest.st_ino,
                            latest.st_size,
                            latest.st_mtime_ns,
                        ) != (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns):
                            raise ValueError("Artwork changed before replacement")
                        safe_path(path, self.cache)
                        safe_path(canonical, self.assets)
                        safe_path(temporary, self.cache)
                        os.replace(temporary, path)
                        if not os.path.samefile(path, canonical):
                            raise OSError("Hard-link verification failed")
                        db.execute(
                            "UPDATE pairs SET status='linked',temporary=NULL,detail='Reclaimed' WHERE path=?",
                            (str(path),),
                        )
                        db.commit()
                        reclaimed += a.st_size
                        linked += 1
                except (OSError, ValueError) as exc:
                    self._issue(db, path, exc)
                    db.execute(
                        "UPDATE pairs SET status='preserved',detail=? WHERE path=?",
                        (str(exc), str(path)),
                    )
                    db.commit()
                finally:
                    if temporary.exists():
                        # Only unlink the hard link we created; never delete an unknown replacement.
                        try:
                            safe_path(temporary, self.cache)
                            safe_path(canonical, self.assets)
                            if os.path.samefile(temporary, canonical):
                                temporary.unlink()
                        except (OSError, ValueError):
                            pass
                report(
                    dict(
                        operation="Reclaiming verified artwork duplicates",
                        current=index + 1,
                        total=len(rows),
                        phase="artwork-cleanup",
                    )
                )
            result = self._summary(db)
            result.update(
                reclaimed_bytes=reclaimed, linked_files=linked, needs_audit=True
            )
            return result

    def _summary(self, db):
        logical, unique, files = 0, 0, 0
        identities = set()
        for row in db.execute("SELECT * FROM files"):
            files += 1
            logical += row["bytes"]
            key = (str(row["device"]), str(row["inode"]))
            if key not in identities:
                unique += row["bytes"]
                identities.add(key)
        counts = dict(db.execute("SELECT status,count(*) FROM pairs GROUP BY status"))
        reclaimable = db.execute(
            "SELECT coalesce(sum(bytes),0) FROM pairs WHERE status='duplicate'"
        ).fetchone()[0]
        issues = db.execute("SELECT count(*) FROM issues").fetchone()[0]
        examples = [
            dict(r) for r in db.execute("SELECT path,detail FROM issues LIMIT 20")
        ]
        return dict(
            root=str(self.root),
            journal=str(self.journal),
            files=files,
            logical_bytes=logical,
            unique_bytes=unique,
            reclaimable_bytes=reclaimable,
            duplicates=counts.get("duplicate", 0),
            already_linked=counts.get("linked", 0),
            preserved=counts.get("preserved", 0),
            problems=issues,
            examples=examples,
            canonical_files=db.execute(
                "SELECT count(*) FROM files WHERE role='canonical'"
            ).fetchone()[0],
            legacy_files=db.execute(
                "SELECT count(*) FROM files WHERE role='legacy'"
            ).fetchone()[0],
            unknown_files=db.execute(
                "SELECT count(*) FROM files WHERE role='unknown'"
            ).fetchone()[0],
        )
