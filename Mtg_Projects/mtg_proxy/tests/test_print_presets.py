import pytest

from models import ProjectState
from services import print_presets
from services.card_edit_service import sheet_capacity


@pytest.mark.parametrize('name', ('Letter 3 x 3', 'A4 3 x 3'))
def test_grid_presets_produce_nine_slots(name):
    state = ProjectState.from_dict({'cards': {'card.png': 1}, 'bleed_edge': '8'})

    print_presets.apply(state, name)

    assert sheet_capacity(state) == (3, 3)
    assert state.extended_guides is True


def test_duplex_and_oversized_presets_apply_expected_settings():
    state = ProjectState()

    print_presets.apply(state, 'Duplex Letter')
    print_presets.apply(state, 'Oversized cards')

    assert state.backside_enabled is True
    assert state.printer_duplex == 'Long edge'
    assert state.oversized_enabled is True


def test_unknown_preset_does_not_change_project():
    state = ProjectState.from_dict({'pagesize': 'A5', 'cards': {'card.png': 1}})
    before = state.to_dict()

    with pytest.raises(ValueError, match='Unknown print preset'):
        print_presets.apply(state, 'Poster')

    assert state.to_dict() == before
