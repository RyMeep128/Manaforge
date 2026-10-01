"""Versioned global printer defaults, independent of rendering and Qt."""
from dataclasses import asdict, dataclass
import math


PAPER_SIZES = ('Letter', 'A5', 'A4', 'A3', 'Legal')
DUPLEX = ('Long edge', 'Short edge', 'Manual / single-sided')
FIELDS = ('pagesize', 'orient', 'backside_enabled', 'backside_offset',
          'backside_vertical_offset', 'backside_pages_at_end',
          'backside_separate_file', 'backside_reverse_page_order', 'printer_duplex')


def validate_printing_settings(settings):
    """Accept legacy named profiles as well as current global settings."""
    if not isinstance(settings, dict):
        raise ValueError('Incomplete printer profile.')
    settings = dict(settings)
    settings.setdefault('backside_vertical_offset', '0')
    if any(key not in settings for key in FIELDS):
        raise ValueError('Incomplete printer profile.')
    if settings['pagesize'] not in PAPER_SIZES or settings['orient'] not in ('Portrait', 'Landscape'):
        raise ValueError('Invalid paper size or orientation.')
    if settings['printer_duplex'] not in DUPLEX:
        raise ValueError('Invalid duplex preference.')
    for key in ('backside_offset', 'backside_vertical_offset'):
        try:
            valid = not isinstance(settings[key], bool) and math.isfinite(float(settings[key]))
        except (ValueError, TypeError, OverflowError):
            valid = False
        if not valid:
            raise ValueError('Backside offsets must be finite numbers.')
    for key in FIELDS:
        if (key.startswith('backside_') and key not in
                ('backside_offset', 'backside_vertical_offset') and
                not isinstance(settings[key], bool)):
            raise ValueError('Invalid backside setting.')
    return {key: settings[key] for key in FIELDS}


@dataclass(frozen=True)
class PrintingPreferences:
    pagesize: str = 'Letter'
    orient: str = 'Portrait'
    backside_enabled: bool = False
    backside_offset: str = '0'
    backside_vertical_offset: str = '0'
    backside_pages_at_end: bool = False
    backside_separate_file: bool = False
    backside_reverse_page_order: bool = False
    printer_duplex: str = 'Long edge'

    def settings(self):
        return validate_printing_settings(asdict(self))

    def to_dict(self):
        return {'version': 1, 'settings': self.settings()}

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict) or type(payload.get('version')) is not int or payload['version'] != 1:
            raise ValueError('Unsupported global printing preferences version.')
        return cls(**validate_printing_settings(payload.get('settings')))
