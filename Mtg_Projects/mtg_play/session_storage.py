"""Bound connection-check storage after owned child processes have stopped.

Call under runtime_distribution.ownership(), including maintenance of old runs.
Unfinished or unconfirmed sessions are deliberately left alone.
"""

import json
from pathlib import Path
import re
import shutil

MAX_SESSIONS = 20
MAX_LOG_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 1024 * 1024
_SESSION = re.compile(r"\d{8}-\d{6}-[0-9a-f]{8}")
_PROCESS = re.compile(r"(?:compiler|bridge|server|peer_\d+)")
_LOGS = ("compile.log", "server.log", "bridge.log", "events.jsonl")


def _linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _closed(session):
    result = session / "result.json"
    if _linked(result) or not result.is_file():
        return False
    with result.open("rb") as stream:
        data = stream.read(MAX_RESULT_BYTES + 1)
    if len(data) > MAX_RESULT_BYTES:
        return False
    value = json.loads(data)
    if not isinstance(value, dict):
        return False
    states = [state for name, state in value.items() if _PROCESS.fullmatch(name)]
    # Early development proofs did not record the compiler. A started bridge
    # establishes that synchronous compilation already finished in those runs.
    compiler_known = "compiler" in value or (
        isinstance(value.get("bridge"), dict) and value["bridge"].get("started") is True
    )
    return (
        compiler_known
        and all(name in value for name in ("bridge", "server"))
        and all(
            isinstance(state, dict)
            and (
                state.get("started") is False
                or state.get("started") is True
                and state.get("reaped") is True
            )
            for state in states
        )
    )


def _remove(path, parent):
    # Check the actual absolute target immediately before recursive removal.
    if _linked(path) or path.resolve().parent != parent.resolve():
        raise OSError("Session cleanup target must be a direct, non-link child")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _compact(session, keep_server):
    # Retain bounded diagnostic tails, never decks, credentials or bootstraps.
    # Preserve one initialized server for xmage_support.find_server's catalog.
    for item in session.iterdir():
        if item.name == "result.json" or keep_server and item.name == "server":
            continue
        if item.name in _LOGS and item.is_file() and not _linked(item):
            with item.open("r+b") as stream:
                stream.seek(0, 2)
                if stream.tell() > MAX_LOG_BYTES:
                    stream.seek(-MAX_LOG_BYTES, 2)
                    tail = stream.read(MAX_LOG_BYTES)
                    stream.seek(0)
                    stream.write(tail)
                    stream.truncate()
            continue
        _remove(item, session)


def prune_sessions(root):
    """Keep 20 completed diagnostics and at most one initialized server.

    Return paths that could not be maintained; storage failures must not replace
    a gameplay result. Unknown directories and uncertain process states survive.
    The caller must hold the gameplay operation lock throughout this call.
    """
    root = Path(root)
    if _linked(root):
        return [str(root)]
    if not root.exists():
        return []
    failures = []
    closed = []
    try:
        for session in sorted(root.iterdir()):
            if (
                not _SESSION.fullmatch(session.name)
                or _linked(session)
                or not session.is_dir()
                or session.resolve().parent != root.resolve()
            ):
                continue
            try:
                if _closed(session):
                    closed.append(session)
            except (OSError, ValueError):
                failures.append(str(session))
        retained = closed[-MAX_SESSIONS:]
        catalog = next(
            (
                session
                for session in reversed(retained)
                if (session / "server/db/cards.h2.mv.db").is_file()
            ),
            None,
        )
        for session in closed:
            try:
                if session not in retained:
                    _remove(session, root)
                else:
                    _compact(session, keep_server=session == catalog)
            except OSError:
                failures.append(str(session))
    except OSError:
        failures.append(str(root))
    return failures
