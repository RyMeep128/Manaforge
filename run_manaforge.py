"""Source and packaged Manaforge entry point, independent of working directory."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
products = root / 'Mtg_Projects'
for directory in (products, products / 'mtg_core'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def main():
    if '--verify-bundle' in sys.argv:
        # CI-only packaged startup check; no provider requests or setup downloads.
        import ijson
        from mtg_core.discovery_starter import starter_data
        from mtg_home.home import HomeWindow
        from PyQt6 import QtWidgets as W
        app = W.QApplication.instance() or W.QApplication(sys.argv)
        if not starter_data().get('cards') or not callable(ijson.items):
            raise RuntimeError('Required packaged data or streaming parser is missing')
        window = HomeWindow()
        app.processEvents()
        window.close()
        return 0
    if '--print-studio' in sys.argv:
        # The legacy printer deliberately owns its own QApplication and event loop.
        proxy = products / 'mtg_proxy'
        if str(proxy) not in sys.path:
            sys.path.insert(0, str(proxy))
        from mtg_proxy.main import gui_qt, main as print_main
        gui_qt.install_exception_handlers()
        print_main()
        return 0
    from mtg_home.launcher import main as home_main
    return home_main()


if __name__ == '__main__':
    try:
        result = main()
    except Exception as exc:
        from PyQt6 import QtWidgets as W
        from mtg_core.diagnostics import get_logger
        get_logger(__name__).exception('Manaforge startup failed')
        if '--verify-bundle' not in sys.argv:
            app = W.QApplication.instance() or W.QApplication(sys.argv)
            W.QMessageBox.critical(None, 'Manaforge could not start', str(exc))
        result = 1
    raise SystemExit(result)
