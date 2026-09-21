from types import SimpleNamespace
import pytest
from mtg_core.decklists import (parse_decklist, resolve_card, resolve_decklist,
                                apply_decklist, export_decklist, DecklistEntry)
from mtg_core.decks import DeckDocument, DeckHistory


def service():
    payload = {'id': 'rock', 'oracle_id': 'oracle', 'name': 'Sol Ring', 'set': 'cmm',
               'collector_number': '410', 'type_line': 'Artifact', 'oracle_text': '{T}: Add {C}{C}.'}
    return SimpleNamespace(get_card=lambda **kw: payload if kw.get('exact_name') == 'Sol Ring' else None,
        get_print=lambda **kw: payload if kw == {'set_code': 'cmm', 'collector_number': '410'} else None,
        database=SimpleNamespace(categorization_data=lambda cards, oracles: {'cards': {'rock': payload}, 'tags': {}}))


def test_sections_counts_printings_and_csv():
    entries, errors = parse_decklist('Commander\n1 Sol Ring (cmm) 410\nDeck\n2x Sol Ring\n'
                                    'SB: 1 Sol Ring\n1 Sol Ring\nMaybeboard\n1 Opt\n0 Bad\n123')
    assert [(e.count, e.section) for e in entries] == [(1, 'commander'), (3, 'mainboard'),
                                                     (1, 'sideboard'), (1, 'considering')]
    assert entries[0].collector_number == '410'
    assert errors == ['0 Bad', '123']
    entries, errors = parse_decklist('section,quantity,name,set_code,collector_number\n'
                                    'commander,1,"Atraxa, Praetors\' Voice",one,196\n'
                                    'sideboard,2,Opt,,\nmainboard,0,Bad,,')
    assert entries[0].name == "Atraxa, Praetors' Voice"
    assert entries[1].section == 'sideboard' and entries[1].set_code is None
    assert errors == ['CSV row 4']


def test_exact_printing_never_silently_falls_back_and_partial_failures_reported():
    with pytest.raises(ValueError, match='local catalog'):
        resolve_card(DecklistEntry(1, 'Sol Ring', 'lea', '1'), service(), allow_remote=False)
    entries, evidence, warnings = resolve_decklist('2 Sol Ring\n1 Missing\n1 Sol Ring (lea) 1', service())
    assert len(entries) == 1 and entries[0].quantity == 2
    assert evidence[entries[0].entry_id][0]['name'] == 'Ramp'
    assert len(warnings) == 2 and '(lea) 1' in warnings[1]


def test_import_undo_merge_manual_protection_export_roundtrip():
    doc = DeckDocument()
    history = DeckHistory(doc)
    result = resolve_decklist('Commander\n1 Sol Ring\nDeck\n2 Sol Ring\nSideboard\n1 Sol Ring', service())
    history.execute(lambda d: apply_decklist(d, result))
    assert len(doc.deck.entries) == 3
    assert doc.deck.commander_entry_ids == [doc.deck.entries[0].entry_id]
    assert all(e.category_ids == ['auto:ramp'] for e in doc.deck.entries)
    parsed, errors = parse_decklist(export_decklist(doc))
    assert not errors
    assert {(e.count, e.section, e.set_code, e.collector_number) for e in parsed} == {
        (1, 'commander', 'cmm', '410'), (2, 'mainboard', 'cmm', '410'), (1, 'sideboard', 'cmm', '410')}
    assert '(' not in export_decklist(doc, include_printings=False, include_sections=False)
    doc.deck.entries[1].category_ids = ['custom']
    doc.deck.entries[1].extras['auto_categories'] = {'manual': True}
    before = doc.to_dict()
    history.execute(lambda d: apply_decklist(d, resolve_decklist('3 Sol Ring', service())))
    assert doc.deck.entries[1].quantity == 5 and doc.deck.entries[1].category_ids == ['custom']
    history.undo()
    assert doc.to_dict() == before
    history.undo()
    assert not doc.deck.entries and not doc.deck.commander_entry_ids


def test_cancellation_has_no_partial_result():
    calls = []
    result = resolve_decklist('1 Sol Ring\n1 Missing', service(),
                             progress=lambda *args: calls.append(args), cancelled=lambda: bool(calls))
    assert result is None and calls == [(1, 2)]
