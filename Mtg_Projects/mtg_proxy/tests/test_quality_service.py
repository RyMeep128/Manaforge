from models import ProjectState
from services import quality_service


class Cards:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_card(self, *, card_id=None, oracle_id=None):
        return self.payloads.get(card_id or oracle_id)

    class Database:
        def __init__(self, records):
            self.records = records

        def get_image_record(self, card_id, variant):
            return self.records.get((card_id, variant))


def state_with_card(metadata=None):
    state = ProjectState.from_dict({'cards': {'card.png': 1}})
    entry = state._ensure_card_entry('card.png')
    entry.card_id = 'card-id'
    if metadata:
        state.set_card_metadata('card.png', metadata)
    return state


def test_basic_land_uses_local_card_payload_when_project_metadata_is_sparse():
    state = state_with_card({'name': 'Island'})
    cards = Cards({'card-id': {'type_line': 'Basic Land — Island'}})

    assert quality_service.is_basic_land(state, 'card.png', cards)


def test_transform_card_without_assigned_back_is_missing_even_with_default():
    state = state_with_card()
    state.backside_enabled = True
    state.backside_default = '__back.png'
    cards = Cards({'card-id': {
        'layout': 'transform',
        'card_faces': [
            {'image_uris': {'large': 'front'}},
            {'image_uris': {'large': 'back'}},
        ],
    }})

    assert quality_service.missing_back(
        state, {'__back.png': {}}, 'card.png', cards)


def test_normal_card_can_use_available_project_default_back():
    state = state_with_card()
    state.backside_default = '__back.png'
    cards = Cards({'card-id': {'layout': 'normal'}})

    assert not quality_service.missing_back(
        state, {'__back.png': {}}, 'card.png', cards)


def test_cached_dfc_back_is_reconnected_without_reimport():
    from types import SimpleNamespace
    state = state_with_card()
    payload = {
        'id': 'card-id', 'layout': 'transform', 'set': 'tst',
        'collector_number': '1',
        'card_faces': [
            {'name': 'Day', 'image_uris': {'large': 'front'}},
            {'name': 'Night', 'image_uris': {'large': 'back'}},
        ],
    }
    cards = Cards({'card-id': payload})
    cards.database = Cards.Database({
        ('card-id', 'back'): SimpleNamespace(asset_id='back-asset')})
    previews = []

    repaired, unresolved = quality_service.recover_cached_backs(
        state, {}, ['card.png'], cards,
        lambda _state, _images, name: previews.append(name))

    assert repaired == ['card.png']
    assert unresolved == []
    assert state.get_card_entry('card.png').backside_asset_id == 'back-asset'
    assert state.backsides['card.png'].startswith('__')
    assert previews == [state.backsides['card.png']]
