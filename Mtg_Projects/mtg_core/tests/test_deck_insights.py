from copy import deepcopy
import pytest
from mtg_core.decks import DeckDocument, DeckEntry, DeckCategory
from mtg_core.deck_insights import deck_insights


def card(eid, qty=1, **facts):
    return DeckEntry(eid, eid, quantity=qty, extras={'facts': facts})


def test_weighted_composition_sections_and_overlapping_roles():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('r', 'Ramp')]
    rock = card('rock', 3, type_line='Artifact Creature — Golem', cmc=2, colors=['G'], mana_cost='{1}{G}')
    rock.category_ids = ['r']
    rock.tags = ['Ramp', 'My plan', 'my plan']
    rock.do_not_print = True
    land = card('land', 5, type_line='Basic Land — Forest', cmc=0, colors=[], mana_cost='')
    commander = card('commander', type_line='Legendary Creature', cmc=5, colors=['W', 'U'], mana_cost='{3}{W/U}{U/P}')
    commander.section = 'commander'
    side = card('side', 7, type_line='Instant', cmc=9, colors=[], mana_cost='{9}')
    side.section = 'sideboard'
    doc.deck.entries = [rock, land, commander, side]
    before = deepcopy(doc.to_dict())
    result = deck_insights(doc)
    assert result['total'] == 9 and result['lands'] == 5
    assert result['curve'] == {2: 3, 5: 1}
    assert result['average_mana_value'] == pytest.approx(2.75)
    assert result['types']['Creature'] == 4 and result['types']['Artifact'] == 3
    assert result['pips'] == {'G': 3, 'W': 1, 'U': 2}
    assert result['roles']['Ramp'] == 3 and result['roles']['My plan'] == 3
    assert deck_insights(doc, sections=('mainboard',))['total'] == 8
    assert doc.to_dict() == before


def test_missing_data_and_dfc_front():
    doc = DeckDocument()
    doc.deck.entries = [card('unknown', 2), DeckEntry('dfc', 'DFC', card_id='dfc')]
    payload = dict(layout='modal_dfc', cmc=3, colors=['R'], card_faces=[
        dict(type_line='Sorcery', colors=['R'], mana_cost='{2}{R}'),
        dict(type_line='Land', colors=[], mana_cost='')])
    result = deck_insights(doc, {'dfc': payload})
    assert result['lands'] == 0 and result['nonlands'] == 1
    assert result['types'] == {'Sorcery': 1}
    assert result['average_mana_value'] == 3
    assert result['unknown']['type'] == 2 and result['unknown']['color'] == 2
    assert result['pips'] == {'R': 1}


def test_manual_roles_are_not_reinferred_and_empty_average_is_unknown():
    doc = DeckDocument()
    doc.deck.entries = [card('land', type_line='Land', cmc=0, mana_cost='', colors=[], oracle_text='{T}: Add {G}.')]
    doc.deck.entries[0].extras['auto_categories'] = {'manual': True}
    result = deck_insights(doc)
    assert result['roles']['Ramp'] == 0
    assert result['average_mana_value'] is None and result['curve'] == {}
    assert deck_insights(DeckDocument())['total'] == 0
