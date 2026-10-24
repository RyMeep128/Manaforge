import pytest
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, QtTest
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.canvas import CardCanvas
from mtg_editor.commander_discovery import DiscoveryCanvas
from mtg_editor.recommendation_panel import RecommendationCanvas
from mtg_editor.gui import EditorWindow
from mtg_ui.card_chrome import quantity_control_rect
from mtg_ui.quantity_preview import QuantityPreview


class Thumbnails(C.QObject):
    updated = C.pyqtSignal()

    def get(self, *args, **kwargs):
        return G.QPixmap()

    def set_visible(self, *args):
        pass


@pytest.mark.parametrize('kind', ['syntax', 'recommendations', 'commander'])
def test_all_discovery_canvases_emit_plus_and_minus(kind):
    app = W.QApplication.instance() or W.QApplication([])
    thumbnails = Thumbnails()
    if kind == 'syntax':
        canvas = CardCanvas(DeckDocument(), thumbnails, search=True)
    elif kind == 'recommendations':
        canvas = RecommendationCanvas(thumbnails)
    else:
        canvas = DiscoveryCanvas(DeckDocument(), thumbnails, None)
    canvas.document.deck.entries = [DeckEntry('one', 'Example', quantity=2)]
    canvas.resize(400, 500)
    canvas.show()
    app.processEvents()
    signals = []
    canvas.quantityRequested.connect(lambda *args: signals.append(args))
    rect = canvas.items[0][1]
    assert canvas.control_rect(rect) == quantity_control_rect(rect)
    for delta in (1, -1):
        button = dict(canvas.quantity_buttons(rect))[delta]
        QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=button.center())
    assert signals == [('one', 1), ('one', -1)]
    canvas.document.deck.entries[0].quantity = 0
    button = dict(canvas.quantity_buttons(rect))[-1]
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=button.center())
    assert len(signals) == 2
    canvas.close()
    canvas.preview.close()


def test_search_minus_updates_only_one_matching_card_and_is_undoable(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    editor.document.deck.entries = [DeckEntry('a', 'Forest', quantity=2, card_id='old-print', oracle_id='forest'),
                                    DeckEntry('b', 'Other', quantity=3, card_id='other')]
    candidate = DeckEntry('result', 'Forest', card_id='new-print', oracle_id='forest')
    editor.search_document.deck.entries = [candidate]
    editor.grid.selected = {'a', 'b'}
    editor.changed()
    editor.add_result('result', -1)
    assert [entry.quantity for entry in editor.document.deck.entries] == [1, 3]
    assert candidate.quantity == 1
    editor.add_result('result', -1)
    assert [entry.entry_id for entry in editor.document.deck.entries] == ['b']
    editor.add_result('result', -1)
    editor.undo()
    assert editor.document.deck.entries[0].quantity == 1
    editor.saved = editor.document.to_dict()
    editor.close()
    app.processEvents()


def test_recommendation_minus_uses_the_same_command(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    candidate = DeckEntry('result', 'Example', card_id='printing', oracle_id='oracle')
    panel = editor.recommendation_panel
    panel.rows = [{'oracle_id': 'oracle', 'entry': candidate, 'roles': []}]
    panel.canvas.document.deck.entries = [candidate]
    panel.add('result', 1)
    panel.add('result', -1)
    assert not editor.document.deck.entries
    editor.undo()
    assert editor.document.deck.entries[0].quantity == 1
    editor.saved = editor.document.to_dict()
    editor.close()
    app.processEvents()


def test_print_preview_shares_control_geometry_and_zero_guard():
    app = W.QApplication.instance() or W.QApplication([])
    preview = QuantityPreview()
    preview.resize(220, 310)
    pixmap = G.QPixmap(180, 252)
    pixmap.fill(G.QColor('green'))
    preview.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
    preview.setPixmap(pixmap)
    preview.quantity_active = True
    preview.quantity = 2
    preview.show()
    app.processEvents()
    signals = []
    preview.quantityRequested.connect(signals.append)
    control = quantity_control_rect(preview.card_rect())
    plus = C.QPoint(control.center().x(), control.top()+5)
    minus = C.QPoint(control.center().x(), control.bottom()-5)
    QtTest.QTest.mouseClick(preview, C.Qt.MouseButton.LeftButton, pos=plus)
    QtTest.QTest.mouseClick(preview, C.Qt.MouseButton.LeftButton, pos=minus)
    assert signals == [1, -1]
    preview.quantity = 0
    QtTest.QTest.mouseClick(preview, C.Qt.MouseButton.LeftButton, pos=minus)
    assert signals == [1, -1]
    preview.close()
