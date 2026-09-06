"""Atomic card-level edits shared by card selection and print preview."""
from constants import page_sizes, card_size_without_bleed_inch
from models import ProjectState
from services import layout_service


def sheet_capacity(state):
    width, height = page_sizes[state.pagesize]
    if state.orient == 'Landscape':
        width, height = height, width
    bleed = max(0, float(state.bleed_edge)) / 25.4
    card_width, card_height = (72 * (v + 2 * bleed) for v in card_size_without_bleed_inch)
    return int(width // card_width), int(height // card_height)


def set_oversized(state, names, enabled, *, placements=None, capacity=None):
    candidate = ProjectState.from_dict(state.to_dict())
    names = set(names).intersection(candidate.cards)
    if not names:
        return 0
    columns, rows = capacity or sheet_capacity(candidate)
    if placements is not None:
        candidate.manual_layout = layout_service.record(placements)
    if enabled:
        candidate.oversized_enabled = True
    for name in names:
        candidate._ensure_card_entry(name).oversized = bool(enabled)
        if enabled:
            candidate.oversized[name] = True
        else:
            candidate.oversized.pop(name, None)
    _, relocated = layout_service.resolve(candidate, columns, rows)
    state.copy_from(candidate)
    return relocated
