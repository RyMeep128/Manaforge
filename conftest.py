from __future__ import annotations

import sys
from pathlib import Path


_WORKSPACE_ROOT = Path(__file__).resolve().parent
_PRODUCTS_ROOT = _WORKSPACE_ROOT / "Mtg_Projects"
_PROXY_ROOT = _PRODUCTS_ROOT / "mtg_proxy"
_CORE_CONTAINER = _PRODUCTS_ROOT / "mtg_core"

for path in (str(_PRODUCTS_ROOT), str(_PROXY_ROOT), str(_CORE_CONTAINER)):
    if path not in sys.path:
        sys.path.insert(0, path)
