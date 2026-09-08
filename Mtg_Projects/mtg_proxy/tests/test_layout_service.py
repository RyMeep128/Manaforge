from copy import deepcopy
import pytest
import pdf
from models import ProjectState
from services import layout_service as layout


def state_with(cards, oversized=()):
    return ProjectState.from_dict(dict(cards=cards, oversized_enabled=True,
        oversized={name: True for name in oversized}))


def test_move_one_duplicate_preserves_gaps_and_roundtrips():
    state = state_with({'a': 3})
    items, _ = layout.resolve(state, 3, 2)
    moved = layout.move(items, items[0]['copy_id'], (2, 1, 2), 3, 2)
    assert moved[1:] == items[1:]
    assert items[0]['page'] == 0
    state.manual_layout = layout.record(moved)
    for serialized in (state.to_dict(), state.to_persisted_dict()):
        loaded = ProjectState.from_dict(serialized)
        replacement = ProjectState()
        replacement.copy_from(loaded)
        assert replacement.manual_layout == state.manual_layout
        pages = pdf.distribute_cards_to_pages(replacement, 3, 2)
        assert len(pages) == 3
        assert not pages[1]['placements']
        assert pdf.distribute_cards_to_grid(pages[0], True, 3, 2)[0][0] is None
        assert pdf.distribute_cards_to_grid(pages[2], True, 3, 2)[1][2][0] == 'a'


def test_swap_and_invalid_targets_are_atomic():
    state = state_with({'a': 1, 'b': 1, 'wide': 1}, ['wide'])
    items, _ = layout.resolve(state, 3, 2)
    wide = next(p for p in items if p['name'] == 'wide')
    regular = next(p for p in items if p['name'] == 'a')
    original = deepcopy(items)
    assert layout.move(items, wide['copy_id'], (0, 0, 2), 3, 2) is None
    assert layout.move(items, wide['copy_id'], (0, 1, -1), 3, 2) is None
    assert layout.move(items, wide['copy_id'], (0, 2, 0), 3, 2) is None
    # Move the wide card onto the second row's single card; the smaller card fits its origin.
    other = next(p for p in items if p['name'] == 'b')
    swapped = layout.move(items, wide['copy_id'], (other['page'], other['row'], other['column']), 3, 2)
    assert swapped is not None
    assert next(p for p in swapped if p['name'] == 'b')['row'] == wide['row']
    # A regular card at the right edge cannot swap with a two-slot footprint.
    assert layout.move(items, regular['copy_id'], (wide['page'], wide['row'], wide['column']), 3, 2) is None
    assert items == original


@pytest.mark.parametrize('source_page', [0, 2])
def test_oversized_swaps_with_two_normal_copies(source_page):
    state = state_with({'wide': 1, 'a': 1, 'b': 1}, ['wide'])
    items = sorted(layout.copies(state).values(), key=lambda p: -p['span'])
    for item, pos in zip(items, [(source_page, 1, 0), (0, 0, 0), (0, 0, 1)]):
        item.update(zip(('page', 'row', 'column'), pos))
    original = deepcopy(items)
    # Input ordering must not reverse the two normal cards.
    swapped = layout.move(list(reversed(items)), items[0]['copy_id'], (0, 0, 0), 3, 2)
    by_id = {p['copy_id']: p for p in swapped}
    assert layout.cells(by_id[items[0]['copy_id']]) == {(0, 0, 0), (0, 0, 1)}
    for column, item in enumerate(items[1:]):
        assert layout.cells(by_id[item['copy_id']]) == {(source_page, 1, column)}
    assert items == original


def test_oversized_collision_with_normal_and_oversized_is_atomic():
    state = state_with({'wide': 2, 'a': 1}, ['wide'])
    items = sorted(layout.copies(state).values(), key=lambda p: -p['span'])
    for item, pos in zip(items, [(0, 1, 0), (0, 0, 1), (0, 0, 0)]):
        item.update(zip(('page', 'row', 'column'), pos))
    original = deepcopy(items)
    assert layout.move(items, items[0]['copy_id'], (0, 0, 0), 3, 2) is None
    assert items == original


def test_reconcile_quantities_sort_and_geometry():
    state = state_with({'a': 3, 'b': 1})
    items, _ = layout.resolve(state, 3, 2)
    state.manual_layout = layout.record(items)
    state.set_card_count('a', 2)
    state.card_sort = 'Alphabetical (Z-A)'
    reconciled, moved = layout.resolve(state, 3, 2)
    assert moved == 0
    assert {p['copy_id'] for p in reconciled} == {p['copy_id'] for p in items if p['name'] != 'a' or p['ordinal'] < 2}
    state.set_card_count('a', 4)
    expanded, _ = layout.resolve(state, 3, 2)
    assert all(p in expanded for p in reconciled)
    state.oversized['a'] = True
    resized, relocated = layout.resolve(state, 2, 2)
    assert relocated > 0
    occupied = set()
    for item in resized:
        assert layout.fits(item, occupied, 2, 2)
        occupied.update(layout.cells(item))
    state.remove_card('a')
    assert [p['name'] for p in layout.resolve(state, 2, 2)[0]] == ['b']


@pytest.mark.parametrize('columns,rows', [(1, 3), (0, 3), (3, 0)])
def test_unprintable_geometry_fails_without_losing_layout(columns, rows):
    state = state_with({'wide': 1}, ['wide'])
    state.manual_layout = layout.record(layout.resolve(state, 3, 2)[0])
    before = deepcopy(state.manual_layout)
    with pytest.raises(ValueError, match='cannot fit'):
        pdf.distribute_cards_to_pages(state, columns, rows)
    assert state.manual_layout == before


@pytest.mark.parametrize('backs_at_end', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
def test_manual_backs_mirror_full_footprint_and_keep_page_sequence(backs_at_end, reverse):
    state = state_with({'wide': 1, 'a': 1}, ['wide'])
    state.backside_enabled = True
    state.backside_pages_at_end = backs_at_end
    state.backside_reverse_page_order = reverse
    state.backsides = {'wide': 'wide-back', 'a': 'a-back'}
    state.backside_short_edge = {'wide': True}
    items, _ = layout.resolve(state, 3, 2)
    wide = next(p for p in items if p['name'] == 'wide')
    wide.update(page=1, row=1, column=1)
    state.manual_layout = layout.record(items)
    pages = pdf.distribute_cards_to_pages(state, 3, 2)
    rendered = pdf.make_render_page_sequence(state, pages)
    backs = [p for p in rendered if p['backside']]
    assert [p['front_page_number'] for p in backs] == ([2, 1] if reverse else [1, 2])
    back = next(p for p in backs if p['front_page_number'] == 2)
    grid = pdf.distribute_cards_to_grid(back['cards'], False, 3, 2)
    assert grid[1][0] == ('wide-back', True, True)
    assert grid[1][1] == (None, None, None)
    assert grid[1][2] is None


def test_legacy_preview_resolution_does_not_enable_manual_layout():
    state = state_with({'a': 1})
    layout.resolve(state, 3, 3)
    assert state.manual_layout is None


def test_occupancy_counts_slots_and_preserves_internal_empty_sheets():
    state = state_with({'a': 1, 'wide': 1}, ['wide'])
    items, _ = layout.resolve(state, 3, 3)
    next(p for p in items if p['name'] == 'a').update(page=3, row=0, column=0)
    pages = layout.occupancy(items, 3, 3)
    assert [p['filled'] for p in pages] == [2, 0, 0, 1]
    assert pages[0]['cards'] == 1
    assert layout.occupancy_label(pages[3]) == 'Page 4: 1/9 filled'
    assert len(layout.occupancy(items, 3, 3, minimum_pages=8)) == 8
    assert layout.occupancy([], 3, 3) == []


def test_history_bounds_branching_and_external_change_invalidation():
    history = layout.LayoutHistory(limit=2)
    snapshots = [dict(project={'revision': i}, extra_pages=0) for i in range(4)]
    history.observe(snapshots[0]['project'])
    for before, after in zip(snapshots, snapshots[1:]):
        history.push(before, after)
        history.observe(after['project'])
    assert len(history.undo_entries) == 2
    assert history.undo() == snapshots[2]
    assert history.redo() == snapshots[3]
    history.undo()
    history.push(snapshots[2], dict(project={'revision': 9}, extra_pages=0))
    assert history.redo() is None
    history.observe({'revision': 10})
    assert history.undo() is None


def test_editor_only_trailing_pages_are_not_exported():
    state = state_with({'a': 1})
    items, _ = layout.resolve(state, 3, 3)
    assert len(layout.pages_from_items(state, items, 3, 3, minimum_pages=5)) == 5
    state.manual_layout = layout.record(items)
    assert len(pdf.distribute_cards_to_pages(state, 3, 3)) == 1


@pytest.mark.parametrize('separate', [False, True])
def test_pdf_drawing_uses_manual_slots_back_offset_and_no_editor_artwork(monkeypatch, separate):
    from services import pdf_service
    from util import mm_to_point
    canvases = []

    class Canvas:
        def __init__(self, path, pagesize):
            self.path, self.pages, self.images = path, [], []
            canvases.append(self)

        def drawImage(self, image, x, y, width, height):
            self.images.append((image, x, y, width, height))

        def showPage(self):
            self.pages.append(self.images)
            self.images = []

        def __getattr__(self, name):
            # Cross guides are the only other drawing operations expected.
            if name in ('setLineWidth', 'setDash', 'setStrokeColorRGB', 'line'):
                return lambda *args: None
            raise AssertionError(f'Unexpected PDF drawing: {name}')

    monkeypatch.setattr(pdf.canvas, 'Canvas', Canvas)
    monkeypatch.setattr(pdf.runtime_images, 'get_processed_path', lambda state, name: name)
    monkeypatch.setattr(pdf.os.path, 'exists', lambda path: True)
    monkeypatch.setattr(pdf, 'get_card_rotation', lambda *args: None)
    state = state_with({'wide': 1}, ['wide'])
    state.backside_enabled = True
    state.backside_separate_file = separate
    state.backside_offset = '2'
    state.backside_vertical_offset = '3'
    state.backsides = {'wide': 'wide-back'}
    item = next(iter(layout.copies(state).values()))
    item.update(page=1, row=1, column=1)
    state.manual_layout = layout.record([item])
    result = pdf_service.generate_pdf(state, (612, 792), 'test.pdf', lambda text: None)
    # Blank page before occupied page is preserved on both sides.
    if separate:
        assert result.backside_pdf_path == 'test_backs.pdf'
        assert [len(c.pages) for c in canvases] == [2, 2]
        assert canvases[0].pages[0] == canvases[1].pages[0] == []
        front, back = canvases[0].pages[1][0], canvases[1].pages[1][0]
    else:
        assert len(canvases[0].pages) == 4
        assert canvases[0].pages[:2] == [[], []]
        front, back = canvases[0].pages[2][0], canvases[0].pages[3][0]
    assert front[0] == 'wide'
    assert back[0] == 'wide-back'
    assert front[3:] == back[3:]
    assert back[1] == pytest.approx(front[1] - front[3] / 2 + mm_to_point(2))
    assert back[2] == pytest.approx(front[2] + mm_to_point(3))
