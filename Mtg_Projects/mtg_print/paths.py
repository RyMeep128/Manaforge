"""Existing print data and bundled-resource locations shared by applications."""
import os
import sys
from pathlib import Path
from mtg_core.paths import data_root

cwd = os.path.abspath(data_root())
os.makedirs(cwd, exist_ok=True)
# Assets still ship with the Proxy application; preserve source/frozen locations.
app_dir = (os.path.dirname(os.path.abspath(sys.executable))
           if getattr(sys, 'frozen', False)
           else str(Path(__file__).resolve().parents[1] / 'mtg_proxy'))
resource_dir = (sys._MEIPASS if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
                else app_dir)
