from __future__ import annotations

import os
import sys
from pathlib import Path


def core_root() -> Path:
    return Path(__file__).resolve().parent.parent


def products_root() -> Path:
    return core_root().parent


def workspace_root() -> Path:
    return products_root().parent


def data_root() -> Path:
    override = os.environ.get("PRINT_PROXY_PREP_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if not root:
            root = str(Path.home() / "AppData" / "Local")
        return Path(root) / "PrintProxyPrep"
    root = os.environ.get("XDG_DATA_HOME")
    if root:
        return Path(root) / "PrintProxyPrep"
    return Path.home() / ".local" / "share" / "PrintProxyPrep"


def core_data_root() -> Path:
    return data_root() / "mtg_core"
