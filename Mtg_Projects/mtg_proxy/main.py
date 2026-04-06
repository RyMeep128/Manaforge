from pathlib import Path
import sys

_APP_ROOT = Path(__file__).resolve().parent
_PRODUCTS_ROOT = _APP_ROOT.parent
_CORE_ROOT = _PRODUCTS_ROOT / "mtg_core"
for _path in (str(_PRODUCTS_ROOT), str(_CORE_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import image
import gui_qt

def main():
    app = gui_qt.init()
    image.init()
    window = gui_qt.window_setup(app)

    gui_qt.event_loop(app)
    app.autosave_managed_session()
    app.close()

if __name__ == "__main__":
    gui_qt.install_exception_handlers()
    main()
