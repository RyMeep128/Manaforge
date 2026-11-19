"""Bounded local Unity diagnostics, independent of disposable session files."""

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import shutil
import uuid

from mtg_core.paths import core_data_root

MAX_SESSIONS = 20
MAX_PLAYER_LOG_BYTES = 4 * 1024 * 1024
_SESSION_NAME = re.compile(r"session-\d{8}T\d{12}Z-[0-9a-f]{32}")


def network_timing_summary(source):
    """Aggregate opt-in measurements without retaining request identifiers or log contents."""
    samples = {}
    stages = {
        "unity_action_received",
        "unity_action_presented",
        "unity_ack_Submitted",
        "unity_ack_Confirmed",
        "engine_complete",
        "gateway_received",
        "gateway_publish_snapshot",
        "layout_refresh",
    }
    for name in ("network-timing.jsonl", "player.log", "seat-0/player.log"):
        path = Path(source) / name
        if path.parent.is_symlink() or path.parent.is_junction():
            continue
        if not path.is_file() or path.is_symlink() or path.is_junction():
            continue
        try:
            with path.open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - MAX_PLAYER_LOG_BYTES))
                lines = (
                    stream.read(MAX_PLAYER_LOG_BYTES)
                    .decode("utf-8", errors="replace")
                    .splitlines()
                )
            for line in lines:
                try:
                    value = json.loads(line.split("MANAFORGE_NETWORK_TIMING ", 1)[-1])
                    if not isinstance(value, dict) or value.get("stage") not in stages:
                        continue
                    elapsed = value.get("elapsed_ms")
                    if (
                        type(elapsed) not in (int, float)
                        or not 0 <= elapsed <= 86400000
                        or not math.isfinite(elapsed)
                    ):
                        continue
                    samples.setdefault(value["stage"], []).append(elapsed)
                except (ValueError, TypeError):
                    continue
        except OSError:
            continue
    result = {}
    for stage, values in samples.items():
        values.sort()
        result[stage] = {
            "count": len(values),
            "p50_ms": round(values[math.ceil(len(values) * 0.5) - 1], 3),
            "p95_ms": round(values[math.ceil(len(values) * 0.95) - 1], 3),
        }
    return result


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
    """Keep player.log, optional timing counters and a summary; never copy bootstraps or decks.

    Caller has stopped owned processes and verified the temporary root's identity.
    Oversized player logs keep their tail so the final exception is preserved.
    """
    source = Path(source)
    log = source / "player.log"
    seat = source / "seat-0"
    if (
        not log.is_file()
        and seat.is_dir()
        and not seat.is_symlink()
        and not seat.is_junction()
    ):
        log = seat / "player.log"
    has_log = log.is_file() and not log.is_symlink() and not log.is_junction()
    timing = source / "network-timing.jsonl"
    has_timing = (
        timing.is_file() and not timing.is_symlink() and not timing.is_junction()
    )
    if not has_log and not has_timing and summary is None and error is None:
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
    client_stop_code = None
    if has_log:
        with log.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            truncated = size > MAX_PLAYER_LOG_BYTES
            stream.seek(max(0, size - MAX_PLAYER_LOG_BYTES))
            data = stream.read(MAX_PLAYER_LOG_BYTES)
        (target / "player.log").write_bytes(data)
        stopped = re.search(
            rb"(?m)^Manaforge (?:channel|receive) stopped: ([A-Z_0-9]{1,100})(?:\s|$)",
            data,
        )
        if stopped:
            client_stop_code = stopped.group(1).decode("ascii")
    if has_timing:
        with timing.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - MAX_PLAYER_LOG_BYTES))
            (target / "network-timing.jsonl").write_bytes(
                stream.read(MAX_PLAYER_LOG_BYTES)
            )
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
    if client_stop_code is not None:
        report["client_stop_code"] = client_stop_code
    failure = source / "game-error.json"
    if (
        failure.is_file()
        and not failure.is_symlink()
        and not failure.is_junction()
        and failure.stat().st_size <= 8192
    ):
        try:
            value = json.loads(failure.read_text(encoding="utf-8"))
            kind = value.get("exception_type")
            frames = value.get("adapter_frames", [])
            if isinstance(kind, str) and re.fullmatch(r"[A-Za-z0-9_$]{1,100}", kind):
                report["adapter_failure"] = (
                    {
                        "exception_type": kind,
                        "frames": [
                            frame
                            for frame in frames[:12]
                            if isinstance(frame, str)
                            and re.fullmatch(r"[A-Za-z0-9_.$<>:]{1,200}", frame)
                        ],
                    }
                    if isinstance(frames, list)
                    else {"exception_type": kind}
                )
        except (OSError, ValueError, AttributeError):
            pass
    timings = network_timing_summary(source)
    if timings:
        report["network_timing"] = timings
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
