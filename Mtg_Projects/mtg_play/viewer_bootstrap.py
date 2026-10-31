"""Private one-time Unity bootstrap. Never log, persist or send to remote peers."""

import json
from pathlib import Path
import re


MAX_BOOTSTRAP_BYTES = 16384


class ViewerBootstrapError(ValueError):
    pass


def export_viewer_bootstrap(
    *,
    port,
    session_id,
    viewer_id,
    engine_version,
    artifact_manifest_sha256,
    viewer_key,
    artwork_directory=None,
    artwork_manifest_sha256=None,
):
    """Return private bytes for an inherited channel, not CLI/env/file delivery.

    The caller creates a fresh seat-only key and owns delivery/lifetime. This
    does not authenticate a peer, connect a socket or export any deck information.
    """

    def matches(value, pattern):
        return isinstance(value, str) and re.fullmatch(pattern, value) is not None

    if (
        type(port) is not int
        or not 1 <= port <= 65535
        or any(
            not matches(value, r"[A-Za-z0-9_.:-]{1,128}")
            for value in (session_id, viewer_id, engine_version)
        )
        or not matches(artifact_manifest_sha256, r"[0-9a-f]{64}")
        or not isinstance(viewer_key, (bytes, bytearray))
        or len(viewer_key) != 32
    ):
        raise ViewerBootstrapError("VIEWER_BOOTSTRAP_INVALID")
    artwork = None
    if artwork_directory is not None or artwork_manifest_sha256 is not None:
        if (
            not isinstance(artwork_directory, str)
            or not artwork_directory
            or len(artwork_directory) > 4096
            or artwork_directory.startswith(("\\\\", "//"))
            or any(ord(char) < 32 for char in artwork_directory)
            or not Path(artwork_directory).is_absolute()
            or not matches(artwork_manifest_sha256, r"[0-9a-f]{64}")
        ):
            raise ViewerBootstrapError("VIEWER_BOOTSTRAP_INVALID")
        artwork = dict(
            directory=artwork_directory, manifest_sha256=artwork_manifest_sha256
        )
    payload = dict(
        viewer_bootstrap_version=1,
        protocol_version=1,
        endpoint=dict(host="127.0.0.1", port=port),
        session_id=session_id,
        viewer_id=viewer_id,
        engine_version=engine_version,
        artifact_manifest_sha256=artifact_manifest_sha256,
        viewer_key_hex=viewer_key.hex(),
        artwork=artwork,
    )
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except UnicodeError:
        raise ViewerBootstrapError("VIEWER_BOOTSTRAP_INVALID") from None
    if len(encoded) > MAX_BOOTSTRAP_BYTES:
        raise ViewerBootstrapError("VIEWER_BOOTSTRAP_INVALID")
    return encoded
