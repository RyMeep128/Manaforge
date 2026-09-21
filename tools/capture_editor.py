"""Capture actual editor widgets with isolated, original demonstration cards."""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'Mtg_Projects'), str(ROOT / 'Mtg_Projects/mtg_core')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_editor.gui import EditorWindow
from mtg_core.decks import DeckEntry, DeckCategory


def main():
    app = W.QApplication([])
    app.setStyle('Fusion')
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    if font_path.exists():
        font_id = G.QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(G.QFont(G.QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    output = ROOT / 'docs/images'
    output.mkdir(exist_ok=True)
    def capture(window, name):
        app.processEvents()
        scale = os.environ.get('QT_SCALE_FACTOR', '')
        suffix = f'-scale-{scale}' if scale else ''
        window.grab().save(str(output / f'{name}{suffix}.png'))
    with tempfile.TemporaryDirectory(prefix='manaforge-editor-capture-') as folder:
        window = EditorWindow(service=object(), root=folder)
        names = ['Canopy Warden', 'Grove Tender', 'River Scholar', 'Ember Sentinel', 'Moonlit Archive',
                 'Verdant Passage', 'Dawn Chorus', 'Tidal Memory', 'Rootbound Sage', 'Prismatic Beacon',
                 'Twilight Grove', 'Stormglass Adept', 'Hearth Guardian', 'Skyward Journey', 'Ancient Crossing']
        colors = ['#326451', '#3c607e', '#80613e', '#65485e']
        for i, name in enumerate(names):
            pix = G.QPixmap(300, 420)
            pix.fill(G.QColor(colors[i % len(colors)]))
            painter = G.QPainter(pix)
            painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
            painter.setPen(G.QColor('#f2eee0'))
            painter.drawRoundedRect(8, 8, 284, 404, 14, 14)
            font = G.QFont('Segoe UI', 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(C.QRect(16, 16, 268, 38), C.Qt.AlignmentFlag.AlignCenter, name)
            painter.setBrush(G.QColor('#20ffffff'))
            painter.drawEllipse(50, 78, 200, 190)
            painter.drawPolygon(G.QPolygon([C.QPoint(38, 240), C.QPoint(143, 90), C.QPoint(263, 240)]))
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(C.QRect(20, 300, 260, 80), C.Qt.AlignmentFlag.AlignCenter,
                             'Original demonstration card\nManaforge visual workspace')
            painter.end()
            entry = DeckEntry(str(i), name, card_id=str(i), quantity=1 if i == 0 else i % 3+1,
                section='commander' if i == 0 else 'mainboard', sort_order=i,
                category_ids=['ramp' if i % 2 else 'draw'],
                extras={'facts': {'type_line': ['Creature', 'Creature', 'Artifact', 'Land'][i % 4], 'cmc': i % 5, 'colors': ['G']}})
            window.document.deck.entries.append(entry)
            window.thumbnails.cache[(str(i), None)] = pix
        window.document.deck.name = 'Canopy Council'
        window.document.deck.format = 'Commander'
        window.document.deck.categories = [DeckCategory('ramp', 'Ramp'), DeckCategory('draw', 'Draw', 1)]
        window.sync_fields()
        window.changed()
        window.resize(1280, 820)
        window.show()
        app.processEvents()
        capture(window, 'deck-editor-grid')
        window.open_search()
        window.search_document.deck.entries = window.document.deck.entries[:6]
        window.results.refresh()
        app.processEvents()
        capture(window, 'deck-editor-search')
        window.toggle_search()
        window.group.setCurrentText('Category')
        window.view_mode.setCurrentText('Stacks')
        app.processEvents()
        capture(window, 'deck-editor-stacks')
        window.resize(640, 360)
        window.open_search()
        app.processEvents()
        capture(window, 'deck-editor-small')
        window.new()
        app.processEvents()
        capture(window, 'deck-editor-empty')
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
