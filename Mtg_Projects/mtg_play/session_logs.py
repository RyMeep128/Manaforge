"""Bounded local Unity diagnostics, independent of disposable session files."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import uuid

from mtg_core.paths import core_data_root

MAX_SESSIONS = 20
MAX_PLAYER_LOG_BYTES = 4 * 1024 * 1024
_SESSION_NAME = re.compile(r"session-\d{8}T\d{12}Z-[0-9a-f]{32}")


def retain_session_logs(
    source,
    *,
    summary=None,
    error=None,
    client_errors=(),
    version=None,
    player=None,
    destination=None,
    payment=None,
    unsupported=None,
    processes=None,
    engine=None,
):
    """Keep player.log and a small summary only; never copy bootstraps or decks.

    Caller has stopped owned processes and verified the temporary root's identity.
    Oversized player logs keep their tail so the final exception is preserved.
    """
    source = Path(source)
    log = source / "player.log"
    has_log = log.is_file() and not log.is_symlink() and not log.is_junction()
    if not has_log and summary is None and error is None:
        return None
    archive = (
        Path(destination)
        if destination is not None
        else core_data_root() / "logs" / "unity-sessions"
    )
    if archive.is_symlink() or archive.is_junction():
        raise OSError("Unity diagnostic directory must not be a link")
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    # Windows can return the same timestamp for consecutive sessions. Keep names
    # ordered by allocation rather than letting a random UUID decide retention.
    previous = max(
        (
            item.name[8:30]
            for item in archive.iterdir()
            if _SESSION_NAME.fullmatch(item.name)
        ),
        default="",
    )
    if stamp <= previous:
        stamp = (
            datetime.strptime(previous, "%Y%m%dT%H%M%S%fZ") + timedelta(microseconds=1)
        ).strftime("%Y%m%dT%H%M%S%fZ")
    target = archive / ("session-" + stamp + "-" + uuid.uuid4().hex)
    target.mkdir(mode=0o700)
    truncated = False
    if has_log:
        with log.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            truncated = size > MAX_PLAYER_LOG_BYTES
            stream.seek(max(0, size - MAX_PLAYER_LOG_BYTES))
            data = stream.read(MAX_PLAYER_LOG_BYTES)
        (target / "player.log").write_bytes(data)
    report = {
        "format_version": 1,
        "saved_at_utc": stamp,
        "app_version": version,
        "player_path": str(player) if player is not None else None,
        "player_log_present": has_log,
        "player_log_truncated": truncated,
        "error_code": error,
        "client_errors": list(client_errors)[-12:],
        "summary": summary,
        "payment": payment,
        "unsupported": unsupported,
        "processes": processes,
    }
    if engine is not None:
        report["engine"] = engine
    (target / "diagnostic.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    # Prune only our own direct, non-link session directories. Never follow links
    # or recursively remove a computed path outside this archive.
    resolved_archive = archive.resolve()
    sessions = sorted(
        item
        for item in archive.iterdir()
        if _SESSION_NAME.fullmatch(item.name)
        and item.is_dir()
        and not item.is_symlink()
        and not item.is_junction()
        and item.resolve().parent == resolved_archive
    )
    for item in sessions[:-MAX_SESSIONS]:
        if item.resolve().parent != resolved_archive:
            continue
        shutil.rmtree(item)
    return target
