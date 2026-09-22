from io import BytesIO
import json
from types import SimpleNamespace
import pytest
from PIL import Image
from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory
from mtg_core.decklists import parse_decklist, resolve_entries, apply_decklist
from mtg_core.deck_sources import parse_blueprint_json, parse_moxfield_json
from mtg_core.project_catalog import project_catalog
from mtg_core.commander import check_commander
from mtg_core.legality import check_constructed, FORMATS
from mtg_core.companions import companion_restriction

NOW = 1800000000


def payload(name='Test', **overrides):
    return {'name': name, 'type_line': 'Creature — Cat', 'oracle_text': '', 'cmc': 2,
            'mana_cost': '{1}{G}', 'color_identity': ['G'], 'legalities': {f.lower(): 'legal' for f in (*FORMATS, 'Commander')}, **overrides}


def test_catalog_combines_decks_projects_and_reports_broken_files(tmp_path):
    decks, projects = tmp_path / 'decks', tmp_path / 'projects'
    decks.mkdir()
    projects.mkdir()
    doc = DeckDocument()
    doc.deck.name = 'Native deck'
    (decks / 'one.manaforge.json').write_text(json.dumps(doc.to_dict()))
    (decks / 'broken.manaforge.json').write_text('{bad')
    project = projects / 'print.json'
    project.write_text(json.dumps({'cards': {'card.png': 2}}))
    (projects / 'library.json').write_text(json.dumps({'projects': [{'path': str(project), 'display_name': 'Print deck'}]}))
    before = project.read_bytes()
    rows, errors = project_catalog(decks, projects)
    assert {r['name'] for r in rows} == {'Native deck', 'Print deck'}
    assert {r['kind'] for r in rows} == {'Deck', 'Print project'}
    assert len(errors) == 1 and project.read_bytes() == before


def test_custom_front_back_art_roundtrip_undo_and_no_merge_loss():
    buf = BytesIO()
    Image.new('RGB', (8, 12), 'green').save(buf, format='PNG')
    stored = []
    card = payload(id='card', oracle_id='oracle')
    def store(content, **kwargs):
        stored.append(kwargs)
        return kwargs['source_url'].rsplit('/', 1)[-1]
    service = SimpleNamespace(get_card=lambda **kwargs: card, fetch_bytes_fn=lambda url: buf.getvalue(),
        store_image_bytes=store, database=SimpleNamespace(categorization_data=lambda *args: {'cards': {'card': card}, 'tags': {}}))
    source, errors = parse_decklist('count,name,image_url,backside_image_url\n1,Test,https://art.example/front,https://art.example/back')
    result = resolve_entries(source, service)
    assert not errors and not result[2]
    assert result[0][0].image_asset_id == 'front' and result[0][0].extras['backside_asset_id'] == 'back'
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('existing', 'Test', card_id='card')]
    history = DeckHistory(doc)
    history.execute(lambda d: apply_decklist(d, result))
    assert len(doc.deck.entries) == 2 and doc.deck.entries[0].quantity == 1
    restored = DeckDocument.from_dict(doc.to_dict())
    assert restored.deck.entries[1].extras['backside_asset_id'] == 'back'
    legacy = restored.apply_to_legacy_proxy()
    custom = legacy['card_entries'][1]
    assert custom['image_asset_id'] == 'front' and custom['backside_asset_id'] == 'back'
    assert custom['backside_name'].startswith('__back_') and custom['backside_pre_cropped']
    history.undo()
    assert len(doc.deck.entries) == 1
    stored.clear()
    result = resolve_entries(source, service, import_artwork=False)
    assert not result[0][0].image_asset_id and not stored
    service.fetch_bytes_fn = lambda url: b'not an image'
    result = resolve_entries(source, service)
    assert not result[0] and len(result[2]) == 1


@pytest.mark.parametrize('parser,body', [
    (parse_blueprint_json, {'payload': {'deck': [{'name': 'Test', 'customImageUrl': 'https://art.example/front'}]}}),
    (parse_moxfield_json, {'mainboard': {'x': {'card': {'name': 'Test'}, 'artOverride': {'front_url': 'https://art.example/front'}}}}),
])
def test_public_source_custom_art(parser, body):
    assert parser(body, preserve_sections=True)[0].image_url == 'https://art.example/front'
    assert parser(body)[0].image_url is None


@pytest.mark.parametrize('name,good,bad', [
    ('Gyruda', payload(cmc=2), payload(cmc=3)),
    ('Jegantha', payload(mana_cost='{1}{G}'), payload(mana_cost='{G}{G}')),
    ('Kaheera', payload(), payload(type_line='Creature — Human')),
    ('Keruga', payload(cmc=3), payload(cmc=2)),
    ('Lurrus', payload(cmc=2), payload(cmc=3)),
    ('Obosh', payload(cmc=3), payload(cmc=2)),
    ('Zirda', payload(oracle_text='{T}: Add {G}.'), payload(oracle_text='Flying')),
])
def test_companion_individual_restrictions(name, good, bad):
    entry = DeckEntry('a', 'Test')
    assert companion_restriction(name, [entry], {'a': good})[:2] == ([], [])
    assert companion_restriction(name, [entry], {'a': bad})[0] == ['a']


def test_companion_group_restrictions_and_missing_data():
    entries = [DeckEntry('a', 'Test'), DeckEntry('b', 'Test')]
    cards = {'a': payload(), 'b': payload()}
    assert companion_restriction('Lutri', entries, cards)[0] == ['a', 'b']
    assert not companion_restriction('Umori', entries, cards)[0]
    cards['b'] = payload(type_line='Instant')
    assert companion_restriction('Umori', entries, cards)[0] == ['a', 'b']
    assert companion_restriction('Yorion', entries, cards)[0]
    entries[0].quantity = 79
    assert not companion_restriction('Yorion', entries, cards, commander=False)[0]
    cards['a'].pop('cmc')
    assert companion_restriction('Gyruda', entries, cards)[1] == ['a']
    assert companion_restriction('New unsupported companion', entries, cards)[1]


def test_commander_companion_pregame_choice_and_print_flags():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('leader', 'Leader', card_id='leader', section='commander'),
        DeckEntry('land', 'Forest', quantity=99, card_id='land'),
        DeckEntry('companion', 'Gyruda, Doom of Depths', card_id='companion', section='sideboard')]
    doc.deck.extras.update(companion_entry_id='companion', commander_colors={'leader': 'G'})
    cards = {'leader': payload('Leader', type_line='Legendary Creature — Human', color_identity=[],
                               oracle_text='If Leader is your commander, choose a color before the game begins.'),
             'land': payload('Forest', type_line='Basic Land — Forest', cmc=0),
             'companion': payload('Gyruda, Doom of Depths', oracle_text='Companion — Your starting deck contains only cards with even mana values.')}
    records = {key: {'payload': p, 'cached_at': NOW} for key, p in cards.items()}
    report = check_commander(doc, records, now=NOW)
    assert report.total == 100 and not report.issues
    cards['leader']['cmc'] = 3
    assert 'companion_restriction' in {i.code for i in check_commander(doc, records, now=NOW).issues}
    doc.deck.extras['commander_colors'] = {}
    assert 'commander_identity' in {i.code for i in check_commander(doc, records, now=NOW).issues}


@pytest.mark.parametrize('format_name', FORMATS)
def test_constructed_size_copies_and_legality(format_name):
    doc = DeckDocument()
    doc.deck.format = format_name
    doc.deck.entries = [DeckEntry('land', 'Forest', quantity=56, card_id='land'),
                        DeckEntry('spell', 'Test', quantity=4, card_id='spell')]
    records = {'land': {'payload': payload('Forest', type_line='Basic Land — Forest'), 'cached_at': NOW},
               'spell': {'payload': payload(), 'cached_at': NOW}}
    assert not check_constructed(doc, records, now=NOW).issues
    doc.deck.entries.append(DeckEntry('side', 'Test', quantity=16, card_id='spell', section='sideboard'))
    records['spell']['payload']['legalities'][format_name.lower()] = 'restricted' if format_name == 'Vintage' else 'banned'
    codes = {i.code for i in check_constructed(doc, records, now=NOW).issues}
    assert {'sideboard', 'copies'} <= codes
    if format_name != 'Vintage':
        assert 'legality' in codes
