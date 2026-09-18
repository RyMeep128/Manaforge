from models import ProjectState
from services import layout_service


def test_do_not_print_flag_round_trips_and_excludes_all_copies():
    state = ProjectState.from_dict({'cards': {'owned.png': 4, 'needed.png': 2}})
    state._ensure_card_entry('owned.png').do_not_print = True

    restored = ProjectState.from_dict(state.to_persisted_dict())
    placements, _ = layout_service.resolve(restored, 3, 3)

    assert restored.get_card_entry('owned.png').do_not_print is True
    assert [item['name'] for item in placements] == ['needed.png', 'needed.png']


def test_excluding_card_reconciles_existing_manual_layout():
    state = ProjectState.from_dict({'cards': {'owned.png': 1, 'needed.png': 1}})
    placements, _ = layout_service.resolve(state, 3, 3)
    state.manual_layout = layout_service.record(placements)

    state._ensure_card_entry('owned.png').do_not_print = True
    reconciled, _ = layout_service.resolve(state, 3, 3)

    assert len(reconciled) == 1
    assert reconciled[0]['name'] == 'needed.png'
