"""Organization model, persistence, and dynamic radial coverage for CI."""
import math
from copy import deepcopy

import pytest
from PyQt6 import QtCore as C, QtWidgets as W, QtTest

from mtg_core.categorization import apply_categories, classify, is_manual
from mtg_core.decks import DeckDocument, DeckCategory, DeckEntry, DeckHistory
from mtg_editor.tag_model import (STARTERS, choices, radial_choices, hold_delay, apply_choice,
                                 rename_choice, delete_choice, retain_tag_definitions)
from mtg_editor.quick_tags import QuickTagMenu, HoldTagGesture
from mtg_editor.tag_management import TagPicker, OrganizationManager


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def populated(count=4):
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory(str(i), f'Role {i}', i) for i in range(count)]
    doc.deck.entries = [DeckEntry(str(i), f'Card {i}', category_ids=[str(i)]) for i in range(count)]
    return doc


def test_empty_starters_are_suggestions_without_persisted_categories():
    doc = DeckDocument()
    assert [c.name for c in choices(doc)] == list(STARTERS)
    assert not doc.deck.categories
    assert choices(doc, tags=True) == []
    first = choices(doc)[0]
    rename_choice(doc, first, 'My plan')
    assert choices(doc)[0].name == 'My plan'
    delete_choice(doc, choices(doc)[1])
    assert len(choices(doc)) == 3
    doc.deck.entries.append(DeckEntry('a', 'First card'))
    assert choices(doc) == []


def test_active_choices_use_all_sections_and_retain_unused_definitions():
    doc = populated()
    doc.deck.categories.append(DeckCategory('unused', 'Unused'))
    doc.deck.entries[0].section = 'sideboard'
    doc.deck.entries[0].tags = ['Angel Synergy', 'angel synergy']
    doc.deck.entries[1].category_ids.append('nonexistent')
    assert len(choices(doc)) == 4
    assert [c.name for c in choices(doc, True)] == ['Angel Synergy']
    retain_tag_definitions(doc)
    doc.deck.entries.pop(0)
    assert 'Role 0' not in [c.name for c in choices(doc)]
    assert 'Role 0' in [c.name for c in choices(doc, active=False)]
    assert not choices(doc, True)
    assert choices(doc, True, active=False)[0].name == 'Angel Synergy'
    assert 'nonexistent' not in {c.key for c in choices(doc)}


def test_radial_matches_primary_groups_not_secondary_auto_roles():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('draw', 'Draw'), DeckCategory('tutor', 'Tutors'),
                           DeckCategory('stax', 'Stax'), DeckCategory('blink', 'Blink'),
                           DeckCategory('commander', 'Commander'), DeckCategory('unused', 'Unused')]
    doc.deck.entries = [DeckEntry('a', 'Draw engine', category_ids=['draw', 'tutor']),
                        DeckEntry('b', 'Restricts opponents', category_ids=['stax']),
                        DeckEntry('c', 'Blinks creatures', category_ids=['blink']),
                        DeckEntry('d', 'Commander', section='commander', category_ids=['commander', 'tutor'])]
    ring, overflow = radial_choices(doc)
    assert {choice.name for choice in ring} == {'Draw', 'Stax', 'Blink'}
    assert not overflow
    assert doc.deck.entries[0].category_ids == ['draw', 'tutor']


def test_order_overflow_inactive_preferences_and_deck_isolation():
    doc = populated(15)
    doc.editor_preferences['quick_menu'] = {'roles_order': ['3', '0', '2', '1'], 'roles_overflow': ['0'],
                                             'hold_delay': 650, 'initial_mode': 'tags'}
    ring, overflow = radial_choices(doc)
    assert [c.key for c in ring][:3] == ['3', '2', '1']
    assert len(ring) == 14
    assert '0' in {c.key for c in overflow}
    doc.deck.entries = [e for e in doc.deck.entries if e.entry_id != '3']
    assert '3' not in {c.key for c in radial_choices(doc)[0]}
    doc.deck.entries.append(DeckEntry('3', 'Restored', category_ids=['3']))
    assert radial_choices(doc)[0][0].key == '3'
    restored = DeckDocument.from_dict(doc.to_dict())
    assert radial_choices(restored) == radial_choices(doc)
    assert hold_delay(restored) == 650
    assert hold_delay(DeckDocument()) == 250
    assert choices(populated())[0].key == '0'


def test_creation_duplicates_rename_delete_history_and_primary_protection():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'One'), DeckEntry('b', 'Two')]
    history = DeckHistory(doc)
    history.execute(lambda d: apply_choice(d, {'a', 'b'}, 'Ramp'))
    key = doc.deck.entries[0].category_ids[0]
    history.execute(lambda d: apply_choice(d, set(), 'RAMP'))
    assert len(doc.deck.categories) == 1
    history.execute(lambda d: apply_choice(d, {'a', 'b'}, 'Angel Synergy', True))
    assert all(e.tags == ['Angel Synergy'] and e.category_ids[0] == key for e in doc.deck.entries)
    choice = choices(doc, True)[0]
    history.execute(lambda d: rename_choice(d, choice, 'Flying team'))
    assert all(e.tags == ['Flying team'] for e in doc.deck.entries)
    role = choices(doc)[0]
    rename_choice(doc, role, 'Mana')
    assert doc.deck.categories[0].category_id == key
    before = deepcopy(doc.to_dict())
    history.execute(lambda d: delete_choice(d, choices(d, True)[0]))
    assert len(doc.deck.entries) == 2 and all(not e.tags for e in doc.deck.entries)
    history.undo()
    assert doc.to_dict() == before
    apply_categories(doc, {'a': classify({}, ['card-draw'])})
    assert doc.deck.entries[0].category_ids[0] == key


def test_extra_tag_does_not_lock_auto_primary_and_unused_creation_stays_hidden():
    doc = populated(1)
    doc.deck.entries[0].category_ids.clear()
    apply_choice(doc, {'0'}, 'Synergy', True)
    assert not is_manual(doc.deck.entries[0])
    apply_categories(doc, {'0': classify({}, ['ramp'])})
    assert choices(doc)[0].name == 'Ramp'
    apply_choice(doc, set(), 'Future role')
    assert 'Future role' not in {c.name for c in choices(doc)}
    assert 'Future role' in {c.name for c in choices(doc, active=False)}


@pytest.mark.parametrize('count', [1, 4, 6, 8, 15])
def test_radial_dynamic_geometry_and_center_cancellation(app, count):
    doc = populated(count)
    menu = QuickTagMenu(doc, {'0'})
    chosen = []
    menu.chosen.connect(lambda *args: chosen.append(args))
    menu.popup(C.QPoint(1, 1))
    assert not menu.findChildren(W.QPushButton)
    assert len(menu.options) == count
    center, outer, inner = menu.geometry_values()
    for i in range(len(menu.options)):
        angle = -math.pi / 2 + i * 2 * math.pi / len(menu.options)
        radius = (inner + outer) / 2
        point = center + C.QPointF(math.cos(angle)*radius, math.sin(angle)*radius)
        assert menu.sector(point) == i
    assert menu.sector(center) is None
    screen = menu.screen().availableGeometry()
    assert screen.contains(menu.geometry())
    QtTest.QTest.mouseRelease(menu, C.Qt.MouseButton.RightButton, pos=center.toPoint())
    assert not chosen and not menu.isVisible()
    menu.deleteLater()


def test_stale_menu_keyboard_and_default_reset(app):
    doc = populated()
    menu = QuickTagMenu(doc, {'0'})
    chosen = []
    menu.chosen.connect(lambda *args: chosen.append(args))
    menu.popup(C.QPoint(400, 400))
    doc.deck.entries.clear()
    menu.choose('Role 0')
    assert chosen == []
    doc = populated()
    menu = QuickTagMenu(doc, {'0'})
    menu.chosen.connect(lambda *args: chosen.append(args))
    menu.popup(C.QPoint(400, 400))
    QtTest.QTest.keyClick(menu, C.Qt.Key.Key_Right)
    QtTest.QTest.keyClick(menu, C.Qt.Key.Key_Return)
    assert chosen == [('Role 0', False)]
    doc.editor_preferences['quick_menu'] = {'hold_delay': 800, 'roles_overflow': ['0']}
    dialog = OrganizationManager(doc)
    dialog.reset()
    dialog.accept()
    assert hold_delay(dialog.draft) == 250
    assert radial_choices(dialog.draft)[0][0].key == '0'
    assert hold_delay(doc) == 800  # Draft remains isolated until accepted by editor.


def test_picker_creation_without_selection_and_gesture_delay(app):
    doc = DeckDocument()
    picker = TagPicker(doc)
    picker.search.setText('My Role')
    assert not picker.assign.isEnabled()
    picker.apply(doc)
    assert doc.deck.categories[0].name == 'My Role'
    assert [c.name for c in choices(doc)] == list(STARTERS)
    picker.mode.setCurrentIndex(1)
    picker.search.setText('My Tag')
    picker.apply(doc)
    assert doc.deck.tags == ['My Tag']
    view = W.QTableView()
    calls = []
    gesture = HoldTagGesture(view, lambda point: None, lambda *args: calls.append(args),
                             lambda *args, **kwargs: calls.append(args), delay=lambda: 700)
    QtTest.QTest.mousePress(view.viewport(), C.Qt.MouseButton.RightButton)
    assert gesture.pending is None and not gesture.timer.isActive() and not calls


def test_toolbar_bulk_assignment_is_one_undo_command(app, tmp_path, monkeypatch):
    from mtg_editor.gui import EditorWindow
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'One'), DeckEntry('b', 'Two')]
    window.changed()
    window.grid.selected = {'a', 'b'}
    def accept_picker(dialog):
        dialog.search.setText('My role')
        return W.QDialog.DialogCode.Accepted
    monkeypatch.setattr(TagPicker, 'exec', accept_picker)
    assert window.add_tag_button.text() == '+ Add Tag'
    window.add_tag_button.click()
    assert len(window.document.deck.categories) == 1
    assert all(is_manual(e) for e in window.document.deck.entries)
    window.undo()
    assert all(not e.category_ids for e in window.document.deck.entries)
    window.saved = window.document.to_dict()
    window.close()
