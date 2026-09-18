from mtg_core.preferences import ArtworkPreferenceRules, choose_print
from mtg_core.services import CardService


def printing(card_id, **values):
    return {'id': card_id, 'oracle_id': 'oracle', 'lang': 'en',
            'released_at': '2020-01-01', 'set': 'set',
            'collector_number': card_id, **values}


def test_precedence_is_explicit_then_favorite_then_rules():
    choices = [printing('old', set='old', released_at='2000-01-01'),
               printing('rule', set='fav'), printing('favorite'), printing('explicit')]
    rules = ArtworkPreferenceRules(preferred_sets=('fav',))

    assert choose_print(choices, explicit_card_id='explicit',
                        favorite_card_id='favorite', rules=rules)['id'] == 'explicit'
    assert choose_print(choices, favorite_card_id='favorite', rules=rules)['id'] == 'favorite'
    assert choose_print(choices, rules=rules)['id'] == 'rule'


def test_avoidance_rules_fall_back_when_every_print_is_avoided():
    promo = printing('promo', promo=True, released_at='2022-01-01')
    normal = printing('normal', promo=False, released_at='2021-01-01')
    rules = ArtworkPreferenceRules(avoid_promos=True)

    assert choose_print([promo, normal], rules=rules)['id'] == 'normal'
    assert choose_print([promo], rules=rules)['id'] == 'promo'


def test_service_persists_oracle_favorite_and_rules(tmp_path):
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'))
    rules = ArtworkPreferenceRules(
        preferred_sets=('neo',), preferred_artists=('Artist',),
        minimum_dpi=600, avoid_textless=True)

    service.set_artwork_favorite('oracle', 'print-id')
    service.set_artwork_preferences(rules)

    reopened = CardService(db_path=str(tmp_path / 'cards.sqlite3'))
    assert reopened.get_artwork_favorite('oracle') == 'print-id'
    assert reopened.get_artwork_preferences() == rules
