from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, QtTest
from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory
from mtg_core.categorization import apply_categories, classify, is_manual
from mtg_editor.quick_tags import QuickTagMenu, apply_quick_role


def test_batch_roles_tags_undo_and_persistence():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'One'), DeckEntry('b', 'Two', tags=['Draw'])]
    ids = {'a', 'b'}
    proposals = {i: classify({}, ['ramp']) for i in ids}
    apply_categories(doc, proposals)
    history = DeckHistory(doc)
    history.execute(lambda d: apply_quick_role(d, ids, 'Protection'))
    assert all(is_manual(e) for e in doc.deck.entries)
    primary = doc.deck.entries[0].category_ids[0]
    history.execute(lambda d: apply_quick_role(d, ids, 'Draw', tags=True))
    assert all(e.tags == ['Draw'] and e.category_ids[0] == primary for e in doc.deck.entries)
    history.execute(lambda d: apply_quick_role(d, ids, 'Draw', tags=True))
    assert all(not e.tags for e in doc.deck.entries)
    history.undo()
    restored = DeckDocument.from_dict(doc.to_dict())
    apply_categories(restored, proposals)
    assert all(e.category_ids[0] == primary and e.tags == ['Draw'] for e in restored.deck.entries)
    apply_categories(restored, proposals, reconsider_manual=True)
    assert all(e.category_ids[0] == 'auto:ramp' and not is_manual(e) for e in restored.deck.entries)


def test_tags_do_not_lock_automatic_primary():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card')]
    apply_quick_role(doc, {'a'}, 'My strategy', tags=True)
    apply_categories(doc, {'a': classify({}, ['ramp'])})
    assert doc.deck.entries[0].category_ids == ['auto:ramp']
    assert doc.deck.entries[0].tags == ['My strategy']


def test_radial_release_modes_cancel_and_custom(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card')]
    menu = QuickTagMenu(doc, {'a'})
    chosen = []
    menu.chosen.connect(lambda *args: chosen.append(args))
    menu.popup(C.QPoint(400, 400))
    QtTest.QTest.mouseRelease(menu, C.Qt.MouseButton.RightButton, pos=C.QPoint(220, 75))
    assert chosen == [('Ramp', False)]
    menu.popup(C.QPoint(400, 400))
    QtTest.QTest.keyClick(menu, C.Qt.Key.Key_Tab)
    QtTest.QTest.mouseRelease(menu, C.Qt.MouseButton.LeftButton, pos=C.QPoint(220, 75))
    assert chosen[-1] == ('Ramp', True)
    menu.popup(C.QPoint(400, 400))
    QtTest.QTest.keyClick(menu, C.Qt.Key.Key_Escape)
    assert len(chosen) == 2 and not menu.isVisible()
    menu.deleteLater()
    app.processEvents()


def test_right_press_preserves_batch_selection_and_history(tmp_path):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'One'), DeckEntry('b', 'Two')]
    window.changed()
    window.show()
    app.processEvents()
    window.grid.selected = {'a', 'b'}
    rect = window.grid.items[-1][1]
    QtTest.QTest.mousePress(window.grid.viewport(), C.Qt.MouseButton.RightButton, pos=rect.center())
    assert not hasattr(window, 'quick_menu')
    QtTest.QTest.qWait(300)
    assert window.quick_menu.ids == {'a', 'b'}
    QtTest.QTest.mouseRelease(window.quick_menu, C.Qt.MouseButton.RightButton, pos=C.QPoint(220, 75))
    assert all(is_manual(e) for e in window.document.deck.entries)
    window.undo()
    assert all(not e.category_ids for e in window.document.deck.entries)
    G.QCursor.setPos(window.grid.viewport().mapToGlobal(C.QPoint(240, 240)))
    QtTest.QTest.keyPress(window.grid, C.Qt.Key.Key_T)
    assert window.quick_menu.isVisible()
    G.QCursor.setPos(window.quick_menu.mapToGlobal(C.QPoint(220, 75)))
    QtTest.QTest.keyRelease(window.quick_menu, C.Qt.Key.Key_T)
    assert all(is_manual(e) for e in window.document.deck.entries)
    window.undo()
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()


def test_open_import_categorizes_without_overwriting_manual(tmp_path):
    from types import SimpleNamespace
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    service = SimpleNamespace(analyze_entries=lambda entries: {
        entry.entry_id: classify({'type_line': 'Artifact', 'oracle_text': '{T}: Add {G}.'})
        for entry in entries})
    window = EditorWindow(service=service, root=tmp_path)
    window.run_task = lambda work, callback: callback(work())
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Mana rock', card_id='card'),
                        DeckEntry('b', 'Manual', extras={'auto_categories': {'manual': True}})]
    window.replace_document(doc)
    assert window.grid.mode == 'Stacks' and window.grid.grouping == 'Category'
    assert doc.deck.entries[0].category_ids == ['auto:ramp']
    assert doc.deck.entries[1].category_ids == []
    window.undo()
    assert doc.deck.entries[0].category_ids == []
    window.saved = doc.to_dict()
    window.close()
    app.processEvents()


def test_review_explicitly_reconsiders_manual():
    from mtg_editor.category_review import CategoryReview
    app = W.QApplication.instance() or W.QApplication([])
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card', extras={'auto_categories': {'manual': True}})]
    dialog = CategoryReview(doc, {'a': classify({}, ['ramp'])})
    assert dialog.selected_proposals() == {}
    dialog.reconsider.setChecked(True)
    assert list(dialog.selected_proposals()) == ['a']
    dialog.reconsider.setChecked(False)
    assert dialog.selected_proposals() == {}
    dialog.close()
    app.processEvents()


def test_click_hold_and_cancellation_in_both_views(tmp_path):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'One'), DeckEntry('b', 'Two')]
    window.changed()
    window.show()
    app.processEvents()
    actions = []
    window.card_menu = lambda *args: actions.append(args)
    for view in (window.grid, window.table):
        window.views.setCurrentWidget(view)
        app.processEvents()
        if view is window.table:
            point = view.visualRect(window.model.index(0, 0)).center()
        else:
            point = window.grid.items[-1][1].center()
        surface = view.viewport()
        QtTest.QTest.mouseClick(surface, C.Qt.MouseButton.RightButton, pos=point)
        assert len(actions) == 1
        context = G.QContextMenuEvent(G.QContextMenuEvent.Reason.Mouse, point, surface.mapToGlobal(point))
        app.sendEvent(surface, context)
        assert len(actions) == 1
        actions.clear()
        for cancel in ('escape', 'move', 'wheel', 'focus'):
            QtTest.QTest.mousePress(surface, C.Qt.MouseButton.RightButton, pos=point)
            if cancel == 'escape':
                QtTest.QTest.keyClick(view, C.Qt.Key.Key_Escape)
            elif cancel == 'move':
                event = G.QMouseEvent(C.QEvent.Type.MouseMove, C.QPointF(point + C.QPoint(40, 0)),
                    C.QPointF(surface.mapToGlobal(point + C.QPoint(40, 0))),
                    C.Qt.MouseButton.NoButton, C.Qt.MouseButton.RightButton, C.Qt.KeyboardModifier.NoModifier)
                app.sendEvent(surface, event)
            elif cancel == 'wheel':
                gesture = window.tag_gestures[0 if view is window.grid else 1]
                gesture.eventFilter(surface, C.QEvent(C.QEvent.Type.Wheel))
            else:
                app.sendEvent(view, G.QFocusEvent(C.QEvent.Type.FocusOut))
            QtTest.QTest.mouseRelease(surface, C.Qt.MouseButton.RightButton, pos=point)
            gesture = window.tag_gestures[0 if view is window.grid else 1]
            assert gesture.pending is None and not gesture.timer.isActive()
            assert not actions
        QtTest.QTest.mousePress(surface, C.Qt.MouseButton.RightButton, pos=point)
        QtTest.QTest.qWait(300)
        assert window.quick_menu.isVisible()
        QtTest.QTest.mouseRelease(window.quick_menu, C.Qt.MouseButton.RightButton, pos=C.QPoint(220, 220))
        assert not window.quick_menu.isVisible()
        assert not actions and all(not e.category_ids for e in window.document.deck.entries)
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()
