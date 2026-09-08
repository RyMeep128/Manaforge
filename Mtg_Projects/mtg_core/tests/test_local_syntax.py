import pytest
from mtg_core import CardService
from mtg_core.db import CardDatabase
from mtg_core.admin_service import CardAdminService
from mtg_core.search import card_rules_text
from mtg_core.search.syntax import LocalQueryError, compile_query


@pytest.fixture
def database(tmp_path):
    db = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    payloads = [
        dict(id='blue', name='Blue Scholar', type_line='Creature — Wizard',
             oracle_text='When this enters, draw a card.', cmc=2, colors=['U'],
             color_identity=['U'], power='1', toughness='2', rarity='common',
             keywords=['Flying'], legalities={'commander': 'legal'}, prices={'usd': '1.25'}),
        dict(id='gold', name='Gold Scholar', type_line='Legendary Creature — Wizard',
             oracle_text='Draw two cards.', cmc=4, colors=['U', 'W'],
             color_identity=['U', 'W'], power='3', toughness='3', rarity='rare'),
        dict(id='rock', name='Quiet Stone', type_line='Artifact', oracle_text='{T}: Add {C}.',
             cmc=1, colors=[], color_identity=[], rarity='uncommon'),
        dict(id='red', name='Red Spark', type_line='Instant', oracle_text='Deal 3 damage.',
             cmc=1, colors=['R'], color_identity=['R'], rarity='common',
             legalities={'commander': 'banned'}),
        dict(id='faces', name='Day // Night', layout='transform', cmc=3,
             color_identity=['G'], card_faces=[
                 dict(name='Day', type_line='Creature — Human', colors=['G'], power='2',
                      toughness='2', oracle_text='Vigilance'),
                 dict(name='Night', type_line='Creature — Wolf', colors=['G'], power='5',
                      toughness='5', oracle_text='Trample. Draw a card.')]),
        dict(id='star', name='Variable Beast', type_line='Creature', cmc=5, colors=['G'],
             color_identity=['G'], power='*', toughness='1+*', rarity='rare'),
    ]
    for payload in payloads:
        payload.update(oracle_id=payload['id'], set='abc', collector_number=payload['id'], lang='en')
        db.upsert_card_payload(payload)
    return db


@pytest.mark.parametrize('query,expected', [
    ('o:"draw a card"', {'blue', 'faces'}),
    ('t:creature mv<=3', {'blue', 'faces'}),
    ('(c:u OR c:r) -t:legendary', {'blue', 'red'}),
    ('-(t:creature OR t:instant)', {'rock'}),
    ('id:u', {'blue', 'rock'}),
    ('ci=wu', {'gold'}),
    ('c:u', {'blue', 'gold'}),
    ('c>u', {'gold'}),
    ('c:g pow>=5', {'faces'}),
    ('c:c', {'rock'}),
    ('c>=c', {'blue', 'gold', 'rock', 'red', 'faces', 'star'}),
    ('c:m', {'gold'}),
    ('c=2', {'gold'}),
    ('id<ug', {'blue', 'faces', 'rock', 'star'}),
    ('f:commander', {'blue'}),
    ('banned:edh', {'red'}),
    ('s:abc r:c', {'blue', 'red'}),
    ('is:dfc t:wolf', {'faces'}),
    ('usd<2', {'blue'}),
    ('pow=0', set()),
    ('!"Blue Scholar"', {'blue'}),
    ('"Gold Scholar"', {'gold'}),
    ('Scholar -name:Gold', {'blue'}),
    ('o:"%"', set()),
    ('kw:flying', {'blue'}),
])
def test_supported_syntax(database, query, expected):
    assert {row.card_id for row in database.search_syntax(query)} == expected


@pytest.mark.parametrize('query', ['o:/draw.*/', 'mv:lots', 't:', 'o:"oops',
                                 '(t:land', 't:land OR', '()', 'c:purple', 'sort:usd'])
def test_invalid_or_unsupported_queries_are_explicit(query):
    with pytest.raises(LocalQueryError):
        compile_query(query)


def test_search_parameters_cannot_change_sql(database):
    assert database.search_syntax('o:"\'); DROP TABLE prints; --"') == []
    assert len(database.search_syntax('')) == 6


def test_full_rules_text_fts_migrates_and_updates(database):
    with database.connect() as connection:
        # Simulate the old name-only search schema, with matching row counts.
        connection.execute('DROP TABLE print_search_fts')
        connection.execute('CREATE VIRTUAL TABLE print_search_fts USING fts5(card_id UNINDEXED, name)')
        connection.execute('INSERT INTO print_search_fts SELECT card_id, name FROM prints')
    migrated = CardDatabase(database.db_path)
    assert {row.card_id for row in migrated.search_prints('trample')} == {'faces'}
    payload = migrated.get_print_by_card_id('blue').payload
    assert payload['oracle_text'] == 'When this enters, draw a card.'
    payload['oracle_text'] = 'Scry 2.'
    migrated.upsert_card_payload(payload)
    assert {row.card_id for row in migrated.search_syntax('o:"draw a card"')} == {'faces'}
    assert {row.card_id for row in migrated.search_prints('scry')} == {'blue'}


def test_local_service_and_admin_search_never_need_network(database):
    def no_network(*args):
        raise AssertionError('Local search must not make network requests')
    service = CardService(db_path=database.db_path, fetch_json_fn=no_network, fetch_bytes_fn=no_network)
    results = service.search_cards('t:creature o:draw', {'scryfall_syntax': True, 'allow_remote': False})
    assert {r.card_id for r in results} == {'blue', 'gold', 'faces'}
    admin = CardAdminService(database=database)
    page = admin.list_prints(query='t:creature o:draw', syntax=True, page_size=1, page=2)
    assert page.total_count == 3
    assert len(page.items) == 1


def test_set_filter_is_applied_before_limit(database):
    assert database.search_syntax('t:creature', limit=1, set_filter='missing') == []


def test_search_returns_one_canonical_print_per_oracle_card(database):
    database.upsert_card_payload(dict(
        id='blue-reprint', oracle_id='blue', name='Blue Scholar',
        type_line='Creature — Wizard', oracle_text='When this enters, draw a card.',
        cmc=2, colors=['U'], color_identity=['U'], set='def', collector_number='7'))
    rows = database.search_syntax('Scholar')
    assert len([row for row in rows if row.oracle_id == 'blue']) == 1


def test_oracle_search_ignores_parenthetical_reminder_text(database):
    database.upsert_card_payload(dict(
        id='reach-reminder', oracle_id='reach-reminder', name='Reach Creature',
        type_line='Creature', oracle_text='Reach (This creature can block creatures with flying.)',
        cmc=2, colors=['G'], color_identity=['G'], set='abc', collector_number='99'))
    database.upsert_card_payload(dict(
        id='flying-text', oracle_id='flying-text', name='Flying Hater',
        type_line='Creature', oracle_text='Destroy target creature with flying.',
        cmc=2, colors=['G'], color_identity=['G'], set='abc', collector_number='100'))
    assert {row.card_id for row in database.search_syntax('o:flying c=g cmc<3')} == {'flying-text'}


def test_oracle_tag_search_uses_local_tag_index(database):
    database.replace_oracle_tags([
        {'label': 'ramp', 'oracle_ids': ['blue', 'rock']},
        {'label': 'card-draw', 'oracle_ids': ['blue']},
    ])
    assert {row.oracle_id for row in database.search_syntax('otag:ramp')} == {'blue', 'rock'}
    assert {row.oracle_id for row in database.search_syntax('otag:ramp -otag:card-draw')} == {'rock'}


def test_parent_oracle_tag_includes_descendant_assignments(database):
    database.replace_oracle_tags([
        {'id': 'parent', 'label': 'ramp', 'child_ids': ['child'], 'taggings': []},
        {'id': 'child', 'label': 'mana-dork', 'child_ids': [],
         'taggings': [{'oracle_id': 'blue'}]},
    ])
    assert {row.oracle_id for row in database.search_syntax('otag:ramp')} == {'blue'}


def test_readable_text_includes_both_faces(database):
    text = card_rules_text(database.get_print_by_card_id('faces').payload)
    assert 'Day' in text and 'Night' in text and 'Vigilance' in text and 'Trample' in text


def test_rules_search_falls_back_without_fts(database):
    with database.connect() as connection:
        connection.execute('DROP TABLE print_search_fts')
    assert {row.card_id for row in database.search_prints('trample')} == {'faces'}


def test_admin_print_edits_preserve_full_payload(database):
    admin = CardAdminService(database=database)
    admin.update_print('blue', oracle_id='blue', name='Renamed Scholar')
    payload = database.get_print_by_card_id('blue').payload
    assert payload['oracle_text'] == 'When this enters, draw a card.'
    assert payload['legalities'] == {'commander': 'legal'}


def test_prints_ui_search_and_full_text(database, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from mtg_core_gui.window import PrintsTab
    app = QApplication.instance() or QApplication([])
    tab = PrintsTab(CardAdminService(database=database), lambda text: None)
    tab.query_edit.setText('o:"draw a card"')
    tab.refresh_table()
    assert tab.table.rowCount() == 2
    tab.table.selectRow(0)
    assert 'draw a card' in tab.rules_edit.toPlainText().lower()
    database.replace_oracle_tags([{'label': 'ramp', 'oracle_ids': ['rock']}])
    tab.query_edit.setText('otag:ramp')
    tab.refresh_table()
    assert tab.table.rowCount() == 1
    assert tab.table.item(0, 1).text() == 'Quiet Stone'
    tab.deleteLater()
    app.processEvents()
