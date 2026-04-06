from __future__ import annotations

from pathlib import Path


def core_root() -> Path:
    return Path(__file__).resolve().parent.parent


def products_root() -> Path:
    return core_root().parent


def workspace_root() -> Path:
    return products_root().parent
