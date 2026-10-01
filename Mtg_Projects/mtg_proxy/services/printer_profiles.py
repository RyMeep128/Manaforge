"""Reusable printer settings, stored independently of card projects."""
import json
from pathlib import Path

from constants import cwd
from mtg_core.printing_preferences import FIELDS, DUPLEX, validate_printing_settings
from models import ProjectState
from util import write_json_atomic
from services import layout_service
from services.card_edit_service import sheet_capacity


def path():
    return Path(cwd) / 'printer_profiles.json'


def validate(settings):
    return validate_printing_settings(settings)


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
    _, relocated = layout_service.resolve(candidate, *sheet_capacity(candidate))
    state.copy_from(candidate)
    return relocated


def summary(settings):
    return '\n'.join(f'{key.replace("_", " ").capitalize()}: {settings[key]}' for key in FIELDS)
