from __future__ import annotations

import sys
import os
from pathlib import Path


_CORE_CONTAINER = Path(__file__).resolve().parent
os.environ.setdefault("PRINT_PROXY_PREP_DATA_DIR", str(_CORE_CONTAINER / ".pytest_tmp_data"))
_PRODUCTS_ROOT = _CORE_CONTAINER.parent

for path in (str(_PRODUCTS_ROOT), str(_CORE_CONTAINER)):
    if path not in sys.path:
        sys.path.insert(0, path)
