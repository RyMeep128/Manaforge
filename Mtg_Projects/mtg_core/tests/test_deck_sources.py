import json
from types import SimpleNamespace
import pytest
from mtg_core.deck_sources import (fetch_public_deck, parse_moxfield_json, parse_blueprint_json,
                                    parse_archidekt_html, _fetch_blueprint_deck)
from mtg_core.decklists import resolve_entries, DecklistEntry, resolve_card

PRINTING = '00000000-0000-4000-8000-000000000001'


@pytest.mark.parametrize('wrapped', [False, True])
def test_moxfield_boards_keep_sections_and_selected_art(wrapped):
    card = {'name': 'Example', 'set': 'PLST', 'collector_number': 'TMP-234', 'scryfall_id': PRINTING}
    boards = {key: {'one': {'quantity': count, 'card': card}} for key, count in
              [('mainboard', 2), ('commanders', 1), ('sideboard', 3), ('maybeboard', 4)]}
    payload = {'boards': {key: {'cards': value} for key, value in boards.items()}} if wrapped else boards
    calls = []
    def fetch(url):
        calls.append(url)
        return payload
    entries = fetch_public_deck('https://moxfield.com/decks/example', fetch_json=fetch)
    assert calls == ['https://api2.moxfield.com/v3/decks/all/example']
    assert {(e.section, e.count) for e in entries} == {
        ('mainboard', 2), ('commander', 1), ('sideboard', 3), ('considering', 4)}
    assert all(e.card_id == PRINTING and e.collector_number == 'TMP-234' and e.set_code == 'plst' for e in entries)
    assert len(parse_moxfield_json(payload)) == 1  # Proxy compatibility flattens sections.


def test_blueprint_public_fetch_sections_and_private_error():
    payload = [{'visibility': 'public', 'payload': {
        'deck': [{'qty': 2, 'card': {'name': 'Card', 'scryfallId': PRINTING}}],
        'commanders': [{'qty': 1, 'card': {'name': 'Commander'}}],
        'considering': [{'qty': 3, 'card': {'name': 'Maybe'}}]}}]
    entries = fetch_public_deck('https://blueprintmtg.io/decks/MyDeck-123', fetch_json=lambda _: payload)
    assert [(e.section, e.count) for e in entries] == [('mainboard', 2), ('considering', 3), ('commander', 1)]
    assert entries[0].card_id == PRINTING
    with pytest.raises(ValueError, match='Private'):
        parse_blueprint_json({'visibility': 'private'}, preserve_sections=True)
    with pytest.raises(ValueError, match='private'):
        parse_blueprint_json([], preserve_sections=True)


def test_archidekt_category_sections_and_printing_identity():
    cards = {str(i): {'name': 'Card', 'qty': i+1, 'setCode': 'plst', 'collectorNumber': 'TMP-234',
                     'uid': PRINTING, 'categories': [category]} for i, category in enumerate(
                         ['Ramp', 'Commander', 'Sideboard', 'Maybeboard', 'Excluded'])}
    payload = {'props': {'pageProps': {'redux': {'deck': {'cardMap': cards}}}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
    entries = fetch_public_deck('https://archidekt.com/decks/123?view=grid', fetch_text=lambda _: html)
    assert [e.section for e in entries] == ['mainboard', 'commander', 'sideboard', 'considering', 'excluded']
    assert all(e.card_id == PRINTING and e.collector_number == 'TMP-234' for e in entries)
    assert len(parse_archidekt_html(html)) == 1


def test_explicit_printing_id_does_not_fall_back_to_name():
    fetched = []
    service = SimpleNamespace(get_card=lambda **kwargs: None,
        fetch_missing_card=lambda **kwargs: fetched.append(kwargs) or {'id': PRINTING})
    entry = DecklistEntry(1, 'Example', card_id=PRINTING)
    with pytest.raises(ValueError, match='artwork/printing'):
        resolve_card(entry, service, allow_remote=False)
    assert not fetched
    assert resolve_card(entry, service, allow_remote=True)['id'] == PRINTING
    assert fetched == [{'card_id': PRINTING}]


def test_url_validation_and_cancellation_before_network():
    calls = []
    fetch = lambda url: calls.append(url)
    for url in ('https://moxfield.com.evil.example/decks/a', 'http://moxfield.com/decks/a', 'file:///deck.json'):
        with pytest.raises(ValueError, match='public'):
            fetch_public_deck(url, fetch_json=fetch, fetch_text=fetch)
    assert fetch_public_deck('https://moxfield.com/decks/a', fetch_json=fetch, cancelled=lambda: True) == []
    assert not calls
    assert _fetch_blueprint_deck('deck-a', fetch_text=lambda url: calls.append(url) or '',
                                 cancelled=lambda: True) == []
    assert len(calls) == 1


def test_malformed_source_does_not_silently_import_partial_deck():
    with pytest.raises(ValueError, match='invalid quantity'):
        parse_moxfield_json({'mainboard': {'a': {'card': {'name': 'Good'}},
            'b': {'quantity': 'bad', 'card': {'name': 'Bad'}}}}, preserve_sections=True)
    with pytest.raises(ValueError, match='payload'):
        parse_blueprint_json({'payload': 'unexpected'}, preserve_sections=True)
