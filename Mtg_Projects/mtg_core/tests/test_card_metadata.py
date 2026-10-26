from types import SimpleNamespace

from mtg_core.card_metadata import card_facts, search_entry


def test_facts_keep_face_fallback_and_do_not_alias_catalog_payload():
    payload = {'color_identity': ['U'], 'legalities': {'commander': 'legal'},
               'card_faces': [{'mana_cost': '{U}', 'oracle_text': 'Draw a card.'}]}
    facts = card_facts(payload)
    assert facts['mana_cost'] == '{U}'
    assert facts['oracle_text'] == 'Draw a card.'
    facts['color_identity'].append('R')
    facts['legalities']['commander'] = 'banned'
    facts['card_faces'][0]['oracle_text'] = 'Changed'
    assert payload['color_identity'] == ['U']
    assert payload['legalities']['commander'] == 'legal'
    assert payload['card_faces'][0]['oracle_text'] == 'Draw a card.'


def test_search_entry_preserves_explicit_category_evidence_without_reclassifying(monkeypatch):
    from mtg_core import categorization
    def unexpected(*args):
        raise AssertionError('Explicit evidence should not be classified again')
    monkeypatch.setattr(categorization, 'classify', unexpected)
    payload = {'mana_cost': '{G}', 'color_identity': ['G'],
               '_category_evidence': [{'name': 'Ramp', 'reason': 'Provided'}]}
    result = SimpleNamespace(card_id='print', name='Example', oracle_id='oracle',
                             set_code='set', collector_number='1', payload=payload)
    entry = search_entry(result)
    assert (entry.entry_id, entry.card_id, entry.oracle_id) == ('print', 'print', 'oracle')
    assert entry.pre_cropped is True
    assert entry.extras['facts']['mana_cost'] == '{G}'
    entry.extras['category_suggestion'][0]['name'] = 'Changed'
    assert payload['_category_evidence'][0]['name'] == 'Ramp'


def test_search_entry_classifies_when_evidence_is_absent(monkeypatch):
    from mtg_core import categorization
    calls = []
    def classify(payload):
        calls.append(payload)
        return ['fallback']
    monkeypatch.setattr(categorization, 'classify', classify)
    result = SimpleNamespace(card_id='print', name='Example', oracle_id=None,
                             set_code=None, collector_number=None, payload=None)
    assert search_entry(result).extras['category_suggestion'] == ['fallback']
    assert calls == [{}]
