"""Focused coverage for card-specific local legality decorations."""
import time
import pytest
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.legality_highlights import card_violations
from mtg_editor.gui import DeckTable, EditorWindow


@pytest.fixture(scope='session', autouse=True)
def app():
    application = W.QApplication.instance() or W.QApplication([])
    yield application
    application.processEvents()


def document(format='Modern', quantity=1):
    doc = DeckDocument()
    doc.deck.format = format
    doc.deck.entries = [DeckEntry('one', 'Example', quantity, card_id='print')]
    return doc


def record(status='legal', **facts):
    payload = dict(name='Example', type_line='Creature', oracle_text='', legalities={'modern': status})
    payload.update(facts)
    return {'print': {'payload': payload, 'cached_at': time.time()}}


def test_illegal_card_and_excess_copies_are_card_specific():
    assert 'one' in card_violations(document(), record('banned'))
    assert 'one' in card_violations(document(quantity=5), record())
    doc = document(quantity=3)
    doc.deck.entries.append(DeckEntry('two', 'Example', 2, section='sideboard', card_id='print'))
    assert set(card_violations(doc, record())) == {'one', 'two'}


def test_unknown_legality_and_deckwide_size_do_not_mark_cards_red():
    assert card_violations(document(), {}) == {}
    assert card_violations(document(), record()) == {}
    assert card_violations(document('Custom', quantity=10), record('banned')) == {}
    assert card_violations(document(quantity=20), record(type_line='Basic Land — Forest')) == {}


def test_table_has_red_foreground_and_explanation_only_for_violations():
    model = DeckTable(document())
    model.violations = {'one': 'Too many copies'}
    index = model.index(0, 1)
    assert model.data(index, C.Qt.ItemDataRole.ForegroundRole).color().name() == '#ff6666'
    assert model.data(index, C.Qt.ItemDataRole.ToolTipRole) == 'Too many copies'
    model.violations.clear()
    assert model.data(index, C.Qt.ItemDataRole.ForegroundRole) is None


def test_async_legality_result_cannot_decorate_a_changed_deck():
    from types import SimpleNamespace
    jobs, applied = [], []
    editor = SimpleNamespace(
        closing=False, task=None, document=document(), _legality_snapshot=None,
        service=SimpleNamespace(get_deck_legality_data=lambda entries: record('banned')),
        run_task=lambda work, show: jobs.append((work, show)),
        _show_card_violations=applied.append,
    )
    EditorWindow._check_card_legality(editor)
    work, show = jobs.pop()
    result = work()
    assert 'one' in result
    editor.document.deck.entries[0].quantity = 2
    show(result)
    assert not applied
    EditorWindow._check_card_legality(editor)
    work, show = jobs.pop()
    show(work())
    assert 'one' in applied[0]
    editor.closing = True
    EditorWindow._check_card_legality(editor)
    assert not jobs
