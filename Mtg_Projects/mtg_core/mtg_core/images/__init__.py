from __future__ import annotations

import hashlib
import os


def checksum_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
