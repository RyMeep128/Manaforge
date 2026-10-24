"""Shared artwork preference rules and deterministic print selection."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class ArtworkPreferenceRules:
    language: str = 'en'
    preferred_sets: tuple[str, ...] = ()
    preferred_year: int | None = None
    preferred_artists: tuple[str, ...] = ()
    preferred_frames: tuple[str, ...] = ()
    preferred_borders: tuple[str, ...] = ()
    preferred_sources: tuple[str, ...] = ()
    minimum_dpi: int = 300
    avoid_promos: bool = False
    avoid_textless: bool = False
    avoid_universes_beyond: bool = False
    avoid_foil_only: bool = False

    @classmethod
    def from_dict(cls, value):
        if value is not None and not isinstance(value, dict):
            raise ValueError('Artwork preferences must be an object.')
        data = dict(value or {})
        tuple_fields = ('preferred_sets', 'preferred_artists', 'preferred_frames',
                        'preferred_borders', 'preferred_sources')
        for key in tuple_fields:
            if data.get(key) is not None and not isinstance(data[key], (list, tuple)):
                raise ValueError(f'{key.replace("_", " ").capitalize()} must be a list.')
            data[key] = tuple(str(item) for item in (data.get(key) or ()))
        if 'language' in data and (not isinstance(data['language'], str) or not data['language'].strip()):
            raise ValueError('Artwork language must be a nonempty string.')
        for key in ('minimum_dpi', 'preferred_year'):
            if key not in data or (key == 'preferred_year' and data[key] is None):
                continue
            if type(data[key]) is not int or not 0 <= data[key] <= 2147483647:
                label = 'Minimum DPI' if key == 'minimum_dpi' else 'Preferred year'
                raise ValueError(f'{label} must be a nonnegative integer up to 2147483647.')
        for key in ('avoid_promos', 'avoid_textless', 'avoid_universes_beyond', 'avoid_foil_only'):
            if key in data and not isinstance(data[key], bool):
                raise ValueError(f'{key.replace("_", " ").capitalize()} must be true or false.')
        allowed = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def to_dict(self):
        result = asdict(self)
        for key in ('preferred_sets', 'preferred_artists', 'preferred_frames',
                    'preferred_borders', 'preferred_sources'):
            result[key] = list(result[key])
        return result


ARTWORK_PROFILE_VERSION = 1


def artwork_profile_rules(payload):
    """Decode version 1 or legacy flat storage without discarding extensions.

    Only a missing database row means default preferences. Invalid stored data
    must be reported instead of silently choosing different artwork.
    """
    if not isinstance(payload, dict):
        raise ValueError('Stored artwork preferences must be an object.')
    if 'version' in payload:
        if type(payload['version']) is not int or payload['version'] != ARTWORK_PROFILE_VERSION:
            raise ValueError('Unsupported artwork preference profile version.')
        rules = payload.get('rules')
        if not isinstance(rules, dict):
            raise ValueError('Stored artwork preference rules must be an object.')
    else:
        rules = payload
    ArtworkPreferenceRules.from_dict(rules)
    return deepcopy(rules)


def artwork_profile_payload(rules, previous=None):
    """Replace known rules while retaining stored fields this version cannot edit."""
    normalized = ArtworkPreferenceRules.from_dict(rules).to_dict()
    stored_rules = artwork_profile_rules(previous) if previous is not None else {}
    result = deepcopy(previous) if previous is not None and 'version' in previous else {}
    known = ArtworkPreferenceRules.__dataclass_fields__
    extensions = {key: value for key, value in stored_rules.items() if key not in known}
    extensions.update(deepcopy(rules))
    extensions.update(normalized)
    result.update(version=ARTWORK_PROFILE_VERSION, rules=extensions)
    return result


def _is_universes_beyond(payload):
    promos = {str(item).casefold() for item in payload.get('promo_types') or ()}
    return ('universes_beyond' in promos or 'universes beyond' in promos
            or bool(payload.get('universes_beyond')))


def avoided(payload, rules):
    finishes = {str(item).casefold() for item in payload.get('finishes') or ()}
    return (
        (rules.avoid_promos and bool(payload.get('promo'))) or
        (rules.avoid_textless and bool(payload.get('textless'))) or
        (rules.avoid_universes_beyond and _is_universes_beyond(payload)) or
        (rules.avoid_foil_only and finishes and finishes <= {'foil', 'etched'})
    )


def _score(payload, rules):
    score = 0
    if str(payload.get('lang') or 'en').casefold() == rules.language.casefold():
        score += 1000
    if bool(payload.get('highres_image')):
        score += 100
    set_code = str(payload.get('set') or '').casefold()
    preferred_sets = [item.casefold() for item in rules.preferred_sets]
    if set_code in preferred_sets:
        score += 800 - preferred_sets.index(set_code)
    artist = str(payload.get('artist') or '').casefold()
    if artist and artist in {item.casefold() for item in rules.preferred_artists}:
        score += 400
    frame = str(payload.get('frame') or '').casefold()
    if frame and frame in {item.casefold() for item in rules.preferred_frames}:
        score += 200
    border = str(payload.get('border_color') or '').casefold()
    if border and border in {item.casefold() for item in rules.preferred_borders}:
        score += 100
    source = str(payload.get('_art_source') or 'scryfall').casefold()
    if source in {item.casefold() for item in rules.preferred_sources}:
        score += 50
    released = str(payload.get('released_at') or '')
    if rules.preferred_year is not None and released[:4].isdigit():
        score += max(0, 100 - abs(int(released[:4]) - rules.preferred_year))
    return score


def choose_print(payloads: Iterable[dict], *, explicit_card_id=None,
                 favorite_card_id=None, rules=None):
    """Explicit project choice -> Oracle favorite -> rules -> stable default."""
    candidates = [dict(payload) for payload in payloads]
    if not candidates:
        return None
    by_id = {str(item.get('id')): item for item in candidates}
    if explicit_card_id and str(explicit_card_id) in by_id:
        return by_id[str(explicit_card_id)]
    if favorite_card_id and str(favorite_card_id) in by_id:
        return by_id[str(favorite_card_id)]
    return rank_prints(candidates, favorite_card_id=None, rules=rules)[0]


def rank_prints(payloads: Iterable[dict], *, favorite_card_id=None, rules=None):
    candidates = [dict(payload) for payload in payloads]
    if not candidates:
        return []
    rules = rules or ArtworkPreferenceRules()
    allowed = [item for item in candidates
               if (favorite_card_id and str(item.get('id')) == str(favorite_card_id))
               or not avoided(item, rules)]
    pool = allowed or candidates
    return sorted(pool, key=lambda item: (
        str(item.get('id')) == str(favorite_card_id),
        _score(item, rules), str(item.get('released_at') or ''),
        str(item.get('set') or ''), str(item.get('collector_number') or ''),
        str(item.get('id') or '')), reverse=True)
