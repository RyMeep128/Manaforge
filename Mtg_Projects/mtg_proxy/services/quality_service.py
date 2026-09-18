"""Local-only project quality queries used by bulk tools and preflight."""
from __future__ import annotations

import card_layouts


def card_payload(state, card_name, card_service=None):
    entry = state.get_card_entry(card_name)
    if entry is None:
        return None
    if card_service is None:
        from mtg_core import get_default_card_service
        card_service = get_default_card_service()
    if entry.card_id:
        payload = card_service.get_card(card_id=entry.card_id)
        if payload:
            return payload
    if entry.oracle_id:
        return card_service.get_card(oracle_id=entry.oracle_id)
    return None


def is_basic_land(state, card_name, card_service=None):
    metadata = state.get_card_metadata(card_name) or {}
    type_line = str(metadata.get('type_line') or '')
    if not type_line:
        payload = card_payload(state, card_name, card_service) or {}
        type_line = str(payload.get('type_line') or '')
    return 'basic land' in type_line.casefold()


def requires_specific_back(state, card_name, card_service=None):
    payload = card_payload(state, card_name, card_service) or {}
    return card_layouts.has_printed_back(payload)


def missing_back(state, img_dict, card_name, card_service=None,
                 ensure_preview=None):
    """True for unavailable assigned backs and DFCs using a generic default."""
    entry = state.get_card_entry(card_name)
    assigned = state.backsides.get(card_name)
    if requires_specific_back(state, card_name, card_service) and not assigned:
        return True
    back_name = assigned or state.backside_default
    if not back_name:
        return True
    if ensure_preview is None:
        return back_name not in img_dict
    return ensure_preview(state, img_dict, back_name) is None


def recover_cached_backs(state, img_dict, card_names, card_service=None,
                         ensure_preview=None):
    """Reconnect cached DFC back assets without downloading or reimporting fronts."""
    if card_service is None:
        from mtg_core import get_default_card_service
        card_service = get_default_card_service()
    import deck_import
    repaired, unresolved = [], []
    for card_name in card_names:
        entry = state.get_card_entry(card_name)
        payload = card_payload(state, card_name, card_service) or {}
        if entry is None or not card_layouts.has_printed_back(payload):
            unresolved.append(card_name)
            continue
        faces = payload.get('card_faces') or []
        face_names = [face.get('name') or card_name for face in faces]
        if len(face_names) < 2:
            unresolved.append(card_name)
            continue
        record = (card_service.database.get_image_record(entry.card_id, 'back')
                  if entry.card_id else None)
        asset_id = entry.backside_asset_id or (
            record.asset_id if record is not None else None)
        if not asset_id:
            unresolved.append(card_name)
            continue
        back_name = deck_import.build_face_image_filename(
            payload, face_names[1], hidden=True)
        state.set_card_image_refs(
            card_name, backside_name=back_name, backside_asset_id=asset_id)
        if ensure_preview is not None:
            ensure_preview(state, img_dict, back_name)
        repaired.append(card_name)
    return repaired, unresolved
