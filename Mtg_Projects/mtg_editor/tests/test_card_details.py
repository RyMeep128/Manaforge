from copy import deepcopy
from types import SimpleNamespace
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, QtTest
from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory
from mtg_editor.card_details import CardDetails, apply_printing


def test_printing_preserves_deck_roles_and_undo_clears_old_art():
    doc = DeckDocument()
    entry = DeckEntry('a', 'Card', quantity=3, card_id='old', oracle_id='oracle',
        category_ids=['ramp'], tags=['favorite'], image_asset_id='custom',
        extras={'auto_categories': {'manual': True}, 'backside_asset_id': 'old-back', 'art_override': {}})
    doc.deck.entries = [entry]
    original = deepcopy(doc.to_dict())
    history = DeckHistory(doc)
    history.execute(lambda d: apply_printing(d, 'a', {'id': 'new', 'oracle_id': 'oracle', 'set': 'abc',
        'collector_number': '5', 'oracle_text': 'New text'}))
    assert entry.card_id == 'new' and entry.set_code == 'abc'
    assert entry.quantity == 3 and entry.category_ids == ['ramp'] and entry.tags == ['favorite']
    assert entry.extras['auto_categories']['manual']
    assert entry.image_asset_id is None and 'backside_asset_id' not in entry.extras
    history.undo()
    assert doc.to_dict() == original


def test_details_flip_and_printing_preview(monkeypatch, tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    def synchronous(self, work, callback):
        self.token += 1
        callback(self.token, work(), '')
    monkeypatch.setattr(CardDetails, 'submit', synchronous)
    image = G.QImage(20, 28, G.QImage.Format.Format_RGB32)
    image.fill(G.QColor('green'))
    path = tmp_path / 'front.png'
    image.save(str(path))
    face = lambda name: {'name': name, 'oracle_text': name + ' rules', 'image_uris': {'normal': name}}
    front = {'id': 'one', 'oracle_id': 'oracle', 'set': 'abc', 'card_faces': [face('Front'), face('Back')]}
    other = dict(front, id='two', set='xyz')
    service = SimpleNamespace(get_card=lambda **kw: front, get_prints=lambda oid, **kw: [front, other],
        ensure_image=lambda *args, **kw: str(path), fetch_bytes_fn=lambda url: path.read_bytes())
    dialog = CardDetails(service, DeckEntry('a', 'Card', card_id='one', oracle_id='oracle'))
    dialog.show()
    assert 'Front rules' in dialog.text.toPlainText() and not dialog.use.isEnabled()
    assert dialog.flip.isVisible()
    dialog.flip.click()
    assert 'Back rules' in dialog.text.toPlainText() and dialog.face == 1
    assert dialog.image.pixmap() is not None
    dialog.printings.setCurrentIndex(1)
    assert dialog.face == 0 and dialog.use.isEnabled()
    picked = []
    dialog.printingChosen.connect(lambda *args: picked.append(args))
    dialog.use.click()
    assert picked[0][0] == 'a' and picked[0][1]['id'] == 'two'
    app.processEvents()


def test_single_click_details_double_click_artwork(tmp_path):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'Card')]
    window.changed()
    window.show()
    app.processEvents()
    canvas = window.grid
    canvas.detailsRequested.disconnect()
    canvas.artworkRequested.disconnect()
    details, artwork = [], []
    canvas.detailsRequested.connect(details.append)
    canvas.artworkRequested.connect(artwork.append)
    point = canvas.items[0][1].center()
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=point)
    QtTest.QTest.qWait(app.doubleClickInterval() + 100)
    assert details == ['a']
    details.clear()
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=point)
    QtTest.QTest.mouseDClick(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=point)
    QtTest.QTest.mouseRelease(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=point)
    QtTest.QTest.qWait(app.doubleClickInterval() + 100)
    assert not details and artwork == ['a']
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton,
        C.Qt.KeyboardModifier.ControlModifier, pos=point)
    assert not canvas.detail_timer.isActive()
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()


def test_background_details_load_without_blocking_ui():
    app = W.QApplication.instance() or W.QApplication([])
    payload = {'id': 'one', 'name': 'Card', 'oracle_id': 'o', 'oracle_text': 'Draw a card.'}
    service = SimpleNamespace(get_card=lambda **kw: payload, get_prints=lambda oid, **kw: [payload],
                              ensure_image=lambda *args, **kw: None)
    dialog = CardDetails(service, DeckEntry('a', 'Card', card_id='one'))
    dialog.show()
    for _ in range(100):
        QtTest.QTest.qWait(10)
        if dialog.image.text() == 'Image unavailable':
            break
    assert dialog.printings.count() == 1
    assert 'Draw a card.' in dialog.text.toPlainText()
    assert dialog.image.text() == 'Image unavailable'
    dialog.close()
    C.QThreadPool.globalInstance().waitForDone()
    app.processEvents()


def test_catalog_fetches_missing_reprints_and_applies_to_deck(monkeypatch, tmp_path):
    from mtg_core.services import CardService
    from mtg_editor.gui import EditorWindow
    from urllib.parse import parse_qs, urlparse
    app = W.QApplication.instance() or W.QApplication([])
    original = {'id': 'original', 'oracle_id': 'oracle', 'name': 'Card', 'set': 'one', 'collector_number': '1'}
    reprint = dict(original, id='reprint', set='two', collector_number='2')
    calls = []
    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            query = parse_qs(urlparse(url).query)
            assert query['q'] == ['oracleid:oracle'] and query['unique'] == ['prints']
            return {'object': 'list', 'data': [original], 'has_more': True, 'next_page': 'https://api.scryfall.com/cards/search?page=2'}
        return {'object': 'list', 'data': [reprint], 'has_more': False}
    service = CardService(db_path=str(tmp_path / 'cards.sqlite'), fetch_json_fn=fetch)
    service.database.upsert_card_payload(original)
    service.ensure_image = lambda *a, **kw: None
    def synchronous(self, work, callback):
        self.token += 1
        callback(self.token, work(), '')
    monkeypatch.setattr(CardDetails, 'submit', synchronous)
    window = EditorWindow(service=service, root=tmp_path / 'decks')
    window.document.deck.entries = [DeckEntry('a', 'Card', card_id='original', oracle_id='oracle', tags=['Keep'])]
    window.changed()
    window.card_details('a')
    dialog = window.details_dialog
    assert dialog.printings.count() == 2 and dialog.printings.isEnabled()
    dialog.printings.setCurrentIndex(1)
    dialog.use.click()
    assert window.document.deck.entries[0].card_id == 'reprint'
    assert window.document.deck.entries[0].tags == ['Keep']
    window.undo()
    assert window.document.deck.entries[0].card_id == 'original'
    assert len(service.get_prints('oracle', allow_remote=True)) == 2
    assert len(calls) == 2  # Reopening reuses the completed catalog lookup.
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()


def test_offline_printings_keep_cached_choices(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    payload = {'id': 'one', 'name': 'Card', 'oracle_id': 'o'}
    alternative = dict(payload, id='two')
    def prints(oracle, *, allow_remote=False):
        if allow_remote:
            raise OSError('Offline')
        return [payload, alternative]
    def synchronous(self, work, callback):
        self.token += 1
        callback(self.token, work(), '')
    monkeypatch.setattr(CardDetails, 'submit', synchronous)
    service = SimpleNamespace(get_card=lambda **kw: payload, get_prints=prints,
                              ensure_image=lambda *a, **kw: None)
    dialog = CardDetails(service, DeckEntry('a', 'Card', card_id='one'))
    assert dialog.printings.count() == 2 and dialog.printings.isEnabled()
    assert 'cached choices' in dialog.status.text()
    dialog.printings.setCurrentIndex(1)
    assert dialog.use.isEnabled() and 'cached choices' in dialog.status.text()
    dialog.close()
    app.processEvents()
