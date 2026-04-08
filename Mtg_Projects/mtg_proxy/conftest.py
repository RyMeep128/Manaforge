from __future__ import annotations

import sys
import os
from pathlib import Path


_PROXY_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PRINT_PROXY_PREP_DATA_DIR", str(_PROXY_ROOT / ".pytest_tmp_data"))
_PRODUCTS_ROOT = _PROXY_ROOT.parent
_CORE_CONTAINER = _PRODUCTS_ROOT / "mtg_core"

for path in (str(_PROXY_ROOT), str(_PRODUCTS_ROOT), str(_CORE_CONTAINER)):
    if path not in sys.path:
        sys.path.insert(0, path)
