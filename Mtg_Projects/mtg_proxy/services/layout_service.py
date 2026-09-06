"""Copy-level print placement shared by the editor and PDF renderer."""
from copy import deepcopy
import json


def copies(state):
    result = {}
    for name, count in state.cards.items():
        entry = state.get_card_entry(name)
        entry_id = entry.entry_id if entry else name
        for ordinal in range(max(0, int(count))):
            copy_id = json.dumps([entry_id, ordinal], ensure_ascii=False)
            result[copy_id] = dict(copy_id=copy_id, entry_id=entry_id,
                                   ordinal=ordinal, name=name,
                                   span=2 if state.oversized_enabled and state.oversized.get(name) else 1)
    return result


def cells(item):
    return {(item['page'], item['row'], item['column'] + offset)
            for offset in range(item['span'])}


def fits(item, occupied, columns, rows):
    return (item['page'] >= 0 and 0 <= item['row'] < rows
            and 0 <= item['column'] <= columns - item['span']
            and not cells(item).intersection(occupied))


def validate_capacity(items, columns, rows):
    if items and (rows < 1 or columns < max(i['span'] for i in items)):
        raise ValueError('The selected sheet cannot fit a required card. Choose a larger sheet or change orientation/oversized settings.')


def first_space(item, occupied, columns, rows):
    page = 0
    while True:
        for row in range(rows):
            for column in range(columns):
                candidate = dict(item, page=page, row=row, column=column)
                if fits(candidate, occupied, columns, rows):
                    return candidate
        page += 1


def record(items):
    return {'version': 1, 'placements': [
        {key: item[key] for key in ('copy_id', 'entry_id', 'ordinal', 'page', 'row', 'column')}
        for item in items]}


def resolve(state, columns, rows):
    """Return placements and relocation count; automatic resolution does not edit state."""
    expected = copies(state)
    validate_capacity(list(expected.values()), columns, rows)
    if state.manual_layout is None:
        import pdf
        pages = pdf.distribute_cards_to_pages(state, columns, rows)
        queues = {}
        for item in expected.values():
            queues.setdefault(item['name'], []).append(item)
        result = []
        for page, data in enumerate(pages):
            grid = pdf.distribute_cards_to_grid(data, True, columns, rows)
            for row, line in enumerate(grid):
                for column, card in enumerate(line):
                    if card and card[0] is not None:
                        result.append(dict(queues[card[0]].pop(0), page=page, row=row, column=column))
        return result, 0
    raw = state.manual_layout
    if not isinstance(raw, dict) or raw.get('version') != 1:
        raise ValueError('Unsupported manual print layout version.')
    occupied, result, displaced = set(), [], []
    prior = raw.get('placements', [])
    if not isinstance(prior, list):
        raise ValueError('Invalid manual print layout placements.')
    valid = [p for p in prior if isinstance(p, dict) and
             all(isinstance(p.get(k), int) for k in ('page', 'row', 'column'))]
    for old in sorted(valid, key=lambda p: (p['page'], p['row'], p['column'])):
        item = expected.pop(old.get('copy_id'), None)
        if item is None:
            continue
        item.update({k: old[k] for k in ('page', 'row', 'column')})
        if fits(item, occupied, columns, rows):
            result.append(item)
            occupied.update(cells(item))
        else:
            displaced.append(item)
    for item in displaced + list(expected.values()):
        placed = first_space(item, occupied, columns, rows)
        result.append(placed)
        occupied.update(cells(placed))
    state.manual_layout = record(result)
    return result, len(displaced)


def move(items, copy_id, destination, columns, rows):
    """Plan an atomic move/swap. None means invalid; input remains untouched."""
    result = deepcopy(items)
    source = next((p for p in result if p['copy_id'] == copy_id), None)
    if source is None:
        return None
    candidate = dict(source, **dict(zip(('page', 'row', 'column'), destination)))
    others = [p for p in result if p is not source]
    hits = [p for p in others if cells(p).intersection(cells(candidate))]
    if len(hits) > 1 and not (
            source['span'] == 2 and len(hits) == 2
            and all(p['span'] == 1 for p in hits)):
        return None
    stationary = [p for p in others if p not in hits]
    occupied = set().union(*(cells(p) for p in stationary))
    if not fits(candidate, occupied, columns, rows):
        return None
    swap_occupied = occupied | cells(candidate)
    for offset, target in enumerate(sorted(hits, key=lambda p: p['column'])):
        swapped = dict(target, page=source['page'], row=source['row'],
                       column=source['column'] + offset)
        if not fits(swapped, swap_occupied, columns, rows):
            return None
        swap_occupied.update(cells(swapped))
        target.update(swapped)
    source.update(candidate)
    return result


def pages_from_items(state, items, columns, rows, minimum_pages=0):
    count = max(minimum_pages, max((p['page'] + 1 for p in items), default=0))
    pages = [dict(regular=[], oversized=[], placements=[]) for _ in range(count)]
    for item in items:
        card = (item['name'], bool(state.backside_short_edge.get(item['name'])), item['span'] == 2)
        pages[item['page']]['placements'].append((item['row'], item['column'], card))
    return pages


def occupancy(items, columns, rows, minimum_pages=0):
    """Physical front-sheet occupancy; oversized copies consume two slots."""
    count = max(minimum_pages, max((item['page'] + 1 for item in items), default=0))
    pages = [dict(page=index + 1, filled=0, capacity=columns * rows, cards=0)
             for index in range(count)]
    for item in items:
        pages[item['page']]['filled'] += item['span']
        pages[item['page']]['cards'] += 1
    return pages


def occupancy_label(page):
    return f"Page {page['page']}: {page['filled']}/{page['capacity']} filled"


class LayoutHistory:
    """Bounded, session-only snapshots. External project changes invalidate history."""
    def __init__(self, limit=100):
        self.limit = limit
        self.undo_entries = []
        self.redo_entries = []
        self.baseline = None

    def observe(self, project):
        if self.baseline is not None and self.baseline != project:
            self.undo_entries.clear()
            self.redo_entries.clear()
        self.baseline = deepcopy(project)

    def push(self, before, after):
        if before == after:
            return
        self.undo_entries.append((deepcopy(before), deepcopy(after)))
        self.undo_entries = self.undo_entries[-self.limit:]
        self.redo_entries.clear()
        self.baseline = deepcopy(after['project'])

    def undo(self):
        if not self.undo_entries:
            return None
        entry = self.undo_entries.pop()
        self.redo_entries.append(entry)
        self.baseline = deepcopy(entry[0]['project'])
        return deepcopy(entry[0])

    def redo(self):
        if not self.redo_entries:
            return None
        entry = self.redo_entries.pop()
        self.undo_entries.append(entry)
        self.baseline = deepcopy(entry[1]['project'])
        return deepcopy(entry[1])
