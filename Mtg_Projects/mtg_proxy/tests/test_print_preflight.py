from models import ProjectState
from services import print_preflight


def test_preflight_reports_occupancy_resolution_back_and_bleed(monkeypatch):
    state = ProjectState.from_dict({
        'cards': {'low.png': 1},
        'backside_enabled': True,
        'backside_default': '__back.png',
        'bleed_edge': '2',
    })
    previews = {
        'low.png': {'effective_dpi': 150, 'data': b'front'},
        '__back.png': None,
    }
    monkeypatch.setattr(
        print_preflight.runtime_images, 'ensure_preview_entry',
        lambda state, images, name: previews.get(name))
    placements = [dict(name='low.png', page=0, row=0, column=0, span=1)]

    issues = print_preflight.analyze(state, {}, placements, 3, 3)

    assert [issue.code for issue in issues] == [
        'occupancy', 'low_resolution', 'missing_back', 'clipping']
    assert issues[0].details == ('Page 1: 1/9 filled',)
    assert '150 DPI' in issues[1].details[0]
    assert not any(issue.blocking for issue in issues)


def test_missing_front_and_invalid_layout_block_output(monkeypatch):
    state = ProjectState.from_dict({'cards': {'missing.png': 1}})
    monkeypatch.setattr(
        print_preflight.runtime_images, 'ensure_preview_entry',
        lambda *args: None)
    placements = [dict(name='missing.png', page=0, row=0, column=0, span=1)]

    issues = print_preflight.analyze(state, {}, placements, 1, 1)
    invalid = print_preflight.invalid_layout_issue(ValueError('cannot fit'))

    assert issues[-1].code == 'missing_art'
    assert issues[-1].blocking is True
    assert invalid.blocking is True
    assert invalid.details == ('cannot fit',)
