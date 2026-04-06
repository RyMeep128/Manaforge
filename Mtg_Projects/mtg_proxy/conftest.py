from __future__ import annotations

import sys
from pathlib import Path


_PROXY_ROOT = Path(__file__).resolve().parent
_PRODUCTS_ROOT = _PROXY_ROOT.parent
_CORE_CONTAINER = _PRODUCTS_ROOT / "mtg_core"

for path in (str(_PROXY_ROOT), str(_PRODUCTS_ROOT), str(_CORE_CONTAINER)):
    if path not in sys.path:
        sys.path.insert(0, path)
