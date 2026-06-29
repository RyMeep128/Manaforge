from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_EDITOR_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTS_ROOT = _EDITOR_ROOT.parent

for path in (str(_PRODUCTS_ROOT), str(_EDITOR_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
