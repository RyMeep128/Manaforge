"""Built-in, validated sheet presets for common printing workflows."""
from copy import deepcopy

from models import ProjectState
from services import layout_service
from services.card_edit_service import sheet_capacity


PRESETS = {
    'Letter 3 x 3': {
        'description': 'US Letter, portrait, no bleed, with cut guides.',
        'settings': {'pagesize': 'Letter', 'orient': 'Portrait',
                     'bleed_edge': '0', 'extended_guides': True},
    },
    'A4 3 x 3': {
        'description': 'A4, portrait, no bleed, with cut guides.',
        'settings': {'pagesize': 'A4', 'orient': 'Portrait',
                     'bleed_edge': '0', 'extended_guides': True},
    },
    'Duplex Letter': {
        'description': 'Letter fronts and backs using long-edge duplex.',
        'settings': {'pagesize': 'Letter', 'orient': 'Portrait',
                     'backside_enabled': True, 'printer_duplex': 'Long edge'},
    },
    '3 mm bleed': {
        'description': 'Add 3 mm of bleed around every card.',
        'settings': {'bleed_edge': '3'},
    },
    'Cut guides': {
        'description': 'Show extended cutting guides.',
        'settings': {'extended_guides': True},
    },
    'Oversized cards': {
        'description': 'Enable two-slot oversized card placement.',
        'settings': {'oversized_enabled': True},
    },
}


def names():
    return tuple(PRESETS)


def details(name):
    try:
        return deepcopy(PRESETS[name])
    except KeyError as exc:
        raise ValueError(f'Unknown print preset: {name}') from exc


def apply(state, name):
    """Apply atomically and reconcile manual placements to the new geometry."""
    candidate = ProjectState.from_dict(state.to_dict())
    preset = details(name)
    for key, value in preset['settings'].items():
        setattr(candidate, key, value)
    columns, rows = sheet_capacity(candidate)
    if columns < 1 or rows < 1:
        raise ValueError('This preset cannot fit a card on the selected sheet.')
    if name in ('Letter 3 x 3', 'A4 3 x 3') and (columns, rows) != (3, 3):
        raise ValueError(f'{name} did not produce a 3 x 3 sheet.')
    _, relocated = layout_service.resolve(candidate, columns, rows)
    state.copy_from(candidate)
    return relocated
