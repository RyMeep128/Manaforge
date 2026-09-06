"""Render real Qt widgets with isolated demo data; no network or user projects.

Run with the Proxy virtualenv from the repository root. Output: docs/images/.
The GIF demonstrates UI states for a move, Undo, and Redo.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory(prefix="mtg-suite-docs-")
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['PRINT_PROXY_PREP_DATA_DIR'] = TEMP.name
sys.path[:0] = [str(ROOT / 'Mtg_Projects/mtg_proxy'), str(ROOT / 'Mtg_Projects/mtg_core')]

from PyQt6 import QtCore, QtGui, QtWidgets
from PIL import Image
import editor_widgets
import image
import ui_theme
from models import ProjectState
from services import layout_service
from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase
from mtg_core_gui.window import CoreAdminMainWindow


def main():
    output = ROOT / 'docs/images'
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    if font_path.exists():
        font_id = QtGui.QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QtGui.QFont(QtGui.QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    app.setStyleSheet(ui_theme.application_stylesheet())
    names = {'Forest study': '#2e644f', 'Island study': '#315b83',
             'Mountain study': '#984a39', 'Plains study': '#947c41',
             'Swamp study': '#614778', 'Oversized study': '#32435d'}
    assets = {}
    for name, color in names.items():
        pixmap = QtGui.QPixmap(250, 350)
        pixmap.fill(QtGui.QColor(color))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor('#c7d9e4'), 2))
        painter.drawRoundedRect(14, 14, 222, 322, 12, 12)
        painter.drawEllipse(65, 70, 120, 120)
        font = app.font()
        font.setPixelSize(22)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(15, 210, 220, 50), QtCore.Qt.AlignmentFlag.AlignCenter, name)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(15, 285, 220, 30), QtCore.Qt.AlignmentFlag.AlignCenter, 'DEMO CARD / NO GAME ART')
        painter.end()
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, 'PNG')
        assets[name] = dict(data=image.encode_cached_image_bytes(bytes(data)), size=(250, 350))
    editor_widgets.runtime_images.ensure_preview_entry = lambda state, cache, name: assets.get(name)
    state = ProjectState.from_dict(dict(cards={name: 1 for name in names},
        oversized_enabled=True, oversized={'Oversized study': True}))
    preview = editor_widgets.PrintPreview(state, {})
    preview.resize(1320, 970)
    preview.show()
    preview._zoom_combo.setCurrentText('50%')
    preview._view_combo.setCurrentText('Single Page')
    app.processEvents()

    def capture():
        app.processEvents()
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        preview.grab().save(buffer, 'PNG')
        import io
        return Image.open(io.BytesIO(bytes(data))).convert('RGB')

    frames = [capture()]
    item = next(p for p in preview._placements if p['name'] == 'Forest study')
    overlay = preview._overlays[0]
    overlay.hovered = (0, item['row'], item['column'])
    preview._selected_copy = item['copy_id']
    overlay.update()
    frames.append(capture())
    overlay.drop_destination = (0, 2, 1)
    overlay.drop_valid = True
    overlay.update()
    frames.append(capture())
    preview.commit_layout(layout_service.move(preview._placements, item['copy_id'], (0, 2, 1), 3, 3))
    preview.refresh_after_edit()
    frames.append(capture())
    frames[-1].save(output / 'print-preview.png')
    preview.undo_layout()
    frames.append(capture())
    preview.redo_layout()
    frames.append(capture())
    frames[0].save(output / 'layout-undo-redo.gif', save_all=True, append_images=frames[1:],
                   duration=[1200, 1200, 1200, 1600, 1600, 1600], loop=0)
    preview.commit_layout(layout_service.move(preview._placements, item['copy_id'], (3, 0, 0), 3, 3))
    preview.refresh_after_edit()
    preview._set_page(3)
    app.processEvents()
    preview.grab().save(str(output / 'underfilled-sheet.png'))
    def capture_warning():
        dialog = app.activeModalWidget()
        dialog.grab().save(str(output / 'export-warning.png'))
        dialog.reject()
    QtCore.QTimer.singleShot(0, capture_warning)
    editor_widgets.confirm_underfilled_export(preview,
        layout_service.occupancy(preview._placements, preview._columns, preview._rows))

    database = CardDatabase(str(Path(TEMP.name) / 'demo.sqlite3'))
    service = CardAdminService(database=database)
    for index, name in enumerate(names):
        service.create_card(oracle_id=f'demo-oracle-{index}', name=name, layout='normal')
        service.create_print(card_id=f'demo-print-{index}', oracle_id=f'demo-oracle-{index}',
                             name=name, set_code='demo', collector_number=str(index + 1))
    admin = CoreAdminMainWindow(service)
    admin.resize(1320, 820)
    admin._db_label.setText('DB: isolated demonstration database')
    admin.show()
    admin.cards_tab.table.selectRow(0)
    app.processEvents()
    admin.grab().save(str(output / 'core-admin.png'))
    admin.close()
    preview.close()
    print(f'Wrote documentation visuals to {output}')


if __name__ == '__main__':
    main()
    # SQLite connection context managers leave cyclic objects for collection.
    # Release those handles before TemporaryDirectory cleanup on Windows.
    import gc
    gc.collect()
