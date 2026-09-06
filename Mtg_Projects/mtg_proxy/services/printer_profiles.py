"""Reusable printer settings, stored independently of card projects."""
import json
import math
from pathlib import Path

from constants import cwd, page_sizes, card_size_without_bleed_inch
from models import ProjectState
from util import write_json_atomic
from services import layout_service

FIELDS = ('pagesize', 'orient', 'backside_enabled', 'backside_offset',
          'backside_pages_at_end', 'backside_separate_file',
          'backside_reverse_page_order', 'printer_duplex')
DUPLEX = ('Long edge', 'Short edge', 'Manual / single-sided')


def path():
    return Path(cwd) / 'printer_profiles.json'


def validate(settings):
    if not isinstance(settings, dict) or any(key not in settings for key in FIELDS):
        raise ValueError('Incomplete printer profile.')
    if settings['pagesize'] not in page_sizes or settings['orient'] not in ('Portrait', 'Landscape'):
        raise ValueError('Invalid paper size or orientation.')
    if settings['printer_duplex'] not in DUPLEX:
        raise ValueError('Invalid duplex preference.')
    if not math.isfinite(float(settings['backside_offset'])):
        raise ValueError('Backside offset must be a finite number.')
    for key in FIELDS:
        if key.startswith('backside_') and key != 'backside_offset' and not isinstance(settings[key], bool):
            raise ValueError('Invalid backside setting.')
    return {key: settings[key] for key in FIELDS}


def load():
    if not path().exists():
        return {}
    data = json.loads(path().read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('profiles'), dict):
        raise ValueError('Unsupported printer profile file.')
    return {name: validate(settings) for name, settings in data['profiles'].items()}


def save_all(profiles):
    validated = {}
    for name, settings in profiles.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Enter a profile name.')
        validated[name] = validate(settings)
    write_json_atomic(str(path()), {'version': 1, 'profiles': validated})


def capture(state, duplex):
    settings = {key: getattr(state, key) for key in FIELDS}
    settings['printer_duplex'] = duplex
    return validate(settings)


def apply(state, settings):
    """Validate and reconcile before changing the live project."""
    candidate = ProjectState.from_dict(state.to_dict())
    for key, value in validate(settings).items():
        setattr(candidate, key, value)
    width, height = page_sizes[candidate.pagesize]
    if candidate.orient == 'Landscape':
        width, height = height, width
    bleed = max(0, float(candidate.bleed_edge)) / 25.4
    card_width, card_height = (72 * (v + 2 * bleed) for v in card_size_without_bleed_inch)
    _, relocated = layout_service.resolve(candidate, int(width // card_width), int(height // card_height))
    state.copy_from(candidate)
    return relocated


def summary(settings):
    return '\n'.join(f'{key.replace("_", " ").capitalize()}: {settings[key]}' for key in FIELDS)
