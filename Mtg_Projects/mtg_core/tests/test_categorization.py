from copy import deepcopy
from mtg_core.categorization import classify, apply_categories, analyze_entries
from mtg_core.decks import DeckDocument, DeckEntry, DeckCategory, DeckHistory
from mtg_core.db import CardDatabase


def test_functional_roles_are_deterministic_and_explainable():
    result = classify({'type_line': 'Artifact'}, ['card-draw', 'ramp', 'unrecognized'])
    assert [r['name'] for r in result] == ['Ramp', 'Draw']
    assert result == classify({'type_line': 'Artifact'}, ['ramp', 'card-draw'])
    assert all('Local Oracle Tags:' in r['reason'] for r in result)
    assert classify({'oracle_text': 'Draw a card.'}) == []  # no guessed text rules


def test_front_face_and_missing_data():
    assert classify({'type_line': 'Sorcery'})[0]['name'] == 'Sorceries'
    assert classify({'type_line': 'Land'}, ['ramp'])[0]['name'] == 'Lands'
    result = classify({'type_line': 'Sorcery // Land', 'card_faces': [
        {'type_line': 'Sorcery'}, {'type_line': 'Land'}]})
    assert result[0]['name'] == 'Sorceries'
    assert classify({}) == []


def test_manual_protection_idempotence_history_and_serialization():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('custom-ramp', 'Ramp')]
    doc.deck.entries = [DeckEntry('auto', 'Automatic', quantity=4, section='commander',
        image_asset_id='exact-art', extras={'oversized': True, 'unknown': 1}),
        DeckEntry('manual', 'Manual', category_ids=['custom-ramp']),
        DeckEntry('empty', 'Explicit uncategorized', extras={'auto_categories': {'manual': True}})]
    proposals = {e.entry_id: classify({}, ['ramp', 'card-draw']) for e in doc.deck.entries}
    history = DeckHistory(doc)
    before = deepcopy(doc.to_dict())
    history.execute(lambda d: apply_categories(d, proposals))
    after = deepcopy(doc.to_dict())
    assert doc.deck.entries[0].category_ids == ['custom-ramp', 'auto:draw']
    assert doc.deck.entries[1].category_ids == ['custom-ramp']
    assert doc.deck.entries[2].category_ids == []
    assert doc.deck.entries[0].image_asset_id == 'exact-art'
    assert doc.deck.entries[0].quantity == 4
    assert doc.deck.entries[0].extras['oversized']
    apply_categories(doc, proposals)
    assert doc.to_dict() == after
    assert DeckDocument.from_dict(after).to_dict() == after
    history.undo()
    assert doc.to_dict() == before
    history.redo()
    assert doc.to_dict() == after


def test_role_update_preserves_additional_associations():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card')]
    apply_categories(doc, {'a': classify({}, ['ramp'])})
    doc.deck.entries[0].category_ids.append('my-secondary')
    apply_categories(doc, {'a': classify({}, ['card-draw'])})
    assert doc.deck.entries[0].category_ids == ['auto:draw', 'my-secondary']


def test_500_entries_use_batched_local_reads(tmp_path):
    db = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    db.upsert_card_payload({'id': 'card', 'oracle_id': 'oracle', 'name': 'Example',
                            'type_line': 'Artifact', 'set': 'abc', 'collector_number': '1'})
    with db.connect() as connection:
        connection.execute("INSERT INTO oracle_tags VALUES ('oracle', 'ramp')")
    entries = [DeckEntry(str(i), 'Example', card_id='card') for i in range(500)]
    calls = []
    connect = db.connect
    def traced():
        connection = connect()
        connection.set_trace_callback(calls.append)
        return connection
    db.connect = traced
    result = analyze_entries(db, entries)
    assert len(result) == 500
    assert all(r[0]['name'] == 'Ramp' for r in result.values())
    assert len([q for q in calls if q.startswith('SELECT')]) == 2
