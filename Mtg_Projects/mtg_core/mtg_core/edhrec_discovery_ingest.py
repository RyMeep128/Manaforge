"""Resumable discovery normalization under the existing EDHREC collector lock."""

from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

from .edhrec_discovery import normalize_discovery, save_discovery_page
from .edhrec_ingest import MAX_BYTES, catalog_index, collector_lock, page_path, write_json
from .paths import core_data_root


def import_cached_discovery(root=None, catalog=None, *, should_cancel=None):
    """User-triggered offline import, using the same lock as the CLI collector."""
    root = Path(root) if root is not None else core_data_root() / "recommendations" / "edhrec-run"
    catalog = Path(catalog) if catalog is not None else core_data_root() / "card_data.sqlite3"
    if not (root / "state.json").exists():
        raise ValueError("No collected EDHREC responses are available. Collect an offline EDHREC snapshot first, then import cached themes.")
    with collector_lock(root):
        try:
            return build_discovery(root, catalog, should_cancel=should_cancel)
        except InterruptedError:
            if should_cancel and should_cancel():
                return dict(status="cancelled")
            raise


def build_discovery(root, catalog, *, should_cancel=None):
    """Normalize explicit cached tag counts without any network requests.

    The existing collector supplies bounded raw responses, polite pacing and
    retry/STOP behavior. This stage can run independently after an old collection,
    including one whose recommendation checkpoint is already complete.
    """
    root, catalog = Path(root), Path(catalog)
    checkpoint = root / "discovery-state.json"
    staging = root / "discovery-staging.sqlite3"
    target = root.parent / "edhrec-discovery.sqlite3"
    source = json.loads((root / "state.json").read_text(encoding="utf-8"))

    def check_stop():
        if should_cancel and should_cancel():
            raise InterruptedError("Theme import cancelled")
        if (root / "STOP").exists():
            raise InterruptedError("STOP file present")

    check_stop()
    pages, missing = {}, []
    for slug in dict.fromkeys(source["slugs"]):
        check_stop()
        page = page_path(f"commanders/{slug}.json")
        cached = root / "responses" / (hashlib.sha256(page.encode()).hexdigest() + ".json.gz")
        if cached.exists():
            stat = cached.stat()
            pages[slug] = (cached, stat.st_size, stat.st_mtime_ns)
        elif slug in source.get("completed", []):
            missing.append(slug)
    catalog_stat = catalog.stat()
    wal = Path(str(catalog) + "-wal")
    wal_stat = (wal.stat().st_size, wal.stat().st_mtime_ns) if wal.exists() else None
    signature = hashlib.sha256(json.dumps([
        str(catalog.resolve()), catalog_stat.st_size, catalog_stat.st_mtime_ns, wal_stat,
        [(slug, size, stamp) for slug, (_, size, stamp) in pages.items()], missing,
    ]).encode()).hexdigest()
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if state.get("signature") == signature and state.get("status") == "complete" and target.exists():
        return state
    if state.get("signature") != signature or not staging.exists():
        staging.unlink(missing_ok=True)
        state = dict(signature=signature, status="new", completed=[], invalid={}, unresolved={}, missing=missing)
    state.update(status="running", last_error=None)
    write_json(checkpoint, state)
    try:
        if missing:
            raise ValueError("Previously collected raw pages are missing; existing discovery snapshot preserved")
        names, ambiguities = catalog_index(catalog)
        completed = set(state["completed"])
        for slug, (cached, _, _) in pages.items():
            check_stop()
            if slug in completed:
                continue
            state["current"] = slug
            write_json(checkpoint, state)
            state["invalid"].pop(slug, None)
            state["unresolved"].pop(slug, None)
            try:
                with gzip.open(cached, "rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("EDHREC response exceeds size limit")
                payload = json.loads(raw)
                name = payload["container"]["json_dict"]["card"]["name"]
                if name.casefold() in ambiguities:
                    raise ValueError(f"Unresolved commander: {name}")
                data = normalize_discovery(payload, lambda name: names.get(name.casefold()), slug)
            except (OSError, EOFError, KeyError, TypeError, ValueError) as exc:
                reason = str(exc)
                if reason.startswith("Unresolved commander:"):
                    name = reason.removeprefix("Unresolved commander: ")
                    state["unresolved"][slug] = dict(reason=reason, candidates={
                        n: ambiguities[n.casefold()] for n in [name, *name.split(" // ")]
                        if n.casefold() in ambiguities})
                else:
                    state["invalid"][slug] = reason
            else:
                save_discovery_page(staging, data, cached.stat().st_mtime)
                state["completed"].append(slug)
            write_json(checkpoint, state)
        if state["invalid"] or not staging.exists():
            raise ValueError("Discovery validation failed; inspect discovery-state.json. Existing snapshot preserved.")
        with closing(sqlite3.connect(staging)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Discovery snapshot failed integrity validation")
            new_keys = {r[0] for r in db.execute("SELECT commander_key FROM commanders")}
            state["themes"] = db.execute("SELECT count(DISTINCT theme_slug) FROM theme_commanders").fetchone()[0]
        if target.exists():
            with closing(sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                old_keys = {r[0] for r in db.execute("SELECT commander_key FROM commanders")}
            if not old_keys <= new_keys:
                raise ValueError("Discovery rebuild would lose previously resolved cohorts; existing snapshot preserved")
        check_stop()
        backup = root / ("discovery-backup-" + uuid.uuid4().hex)
        backup.mkdir()
        shutil.copy2(checkpoint, backup / checkpoint.name)
        if target.exists():
            with closing(sqlite3.connect(target)) as source_db, closing(sqlite3.connect(backup / target.name)) as dest:
                source_db.backup(dest)
        state.update(status="complete", current=None, cohorts=len(new_keys), backup=str(backup))
        published = False
        try:
            staging.replace(target)
            published = True
            write_json(checkpoint, state)
        except BaseException:
            if published:
                if (backup / target.name).exists():
                    shutil.copy2(backup / target.name, target)
                else:
                    target.unlink(missing_ok=True)
            raise
    except BaseException as exc:
        state.update(status="stopped", last_error=f"{type(exc).__name__}: {exc}")
        write_json(checkpoint, state)
        raise
    return state
