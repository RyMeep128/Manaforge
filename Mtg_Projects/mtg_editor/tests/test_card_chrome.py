from copy import deepcopy
from mtg_core.decks import DeckEntry, DeckCategory
from mtg_editor.card_chrome import corner_colors, marker_color


def test_corner_identity_survives_category_rename_and_does_not_change_assignments():
    category = DeckCategory('my-stable-role', 'Ramp')
    entry = DeckEntry('card', 'Card', quantity=34, category_ids=[category.category_id],
                      tags=['Favorite', 'Angel synergy'], extras={'auto_categories': {'manual': True}})
    before = deepcopy(entry.to_dict())
    colors = {category.category_id: marker_color('role:' + category.category_id)}
    first = corner_colors(entry, colors)
    category.name = 'Mana'
    assert corner_colors(entry, colors) == first
    assert len(first[1]) == 2
    assert entry.to_dict() == before


def test_tag_only_and_untagged_cards_have_corner_fallbacks():
    entry = DeckEntry('card', 'Card', tags=['Favorite', 'favorite'])
    primary, secondary = corner_colors(entry, {})
    assert primary == marker_color('tag:favorite') and secondary == []
    entry.tags.clear()
    assert corner_colors(entry, {}) == ('#52606b', [])
