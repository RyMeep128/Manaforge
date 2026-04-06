from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from mtg_core.admin_service import CardAdminService
from mtg_core_gui.window import CoreAdminMainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = CoreAdminMainWindow(CardAdminService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
