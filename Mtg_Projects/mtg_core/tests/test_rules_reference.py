"""Offline fixtures exercise parsing, atomic installation, and service boundaries."""
from copy import deepcopy
import sqlite3
import pytest

from mtg_core.rules_reference import RulesStore, parse_rules, RULES_PAGE
from mtg_core.services import CardService


DOCUMENT = '''Magic: The Gathering Comprehensive Rules
These rules are effective as of September 25, 2026.
Contents
1. Game Concepts
100. General
7. Additional Rules
702. Keyword Abilities
9. Casual Variants
903. Commander
Glossary
Credits

1. Game Concepts
100. General
100.1. This synthetic test rule introduces the game.
100.1a An example subrule refers to rule 702.9a.
Example: Preserve this example with its subrule.

7. Additional Rules
702. Keyword Abilities
702.1. Abilities follow their individual rules.
702.9. Flying
702.9a This synthetic flying rule refers to rule 100.1a.
702.9b Another flying rule.
702.90. A different numbered ability
702.90a This is not part of rule 702.9.

9. Casual Variants
903. Commander
903.1. This synthetic rule describes the Commander variant.

Glossary
Flying
See rule 702.9.
Credits
Synthetic fixture, not an official rules snapshot.
'''


def test_parser_skips_contents_keeps_examples_and_indexes_keywords():
    effective, rows, keywords = parse_rules(DOCUMENT.replace('\n', '\r\n'))
    assert effective == '2026-09-25'
    assert len([row for row in rows if row['number'] == '100']) == 1
    assert 'Preserve this example' in next(row['body'] for row in rows if row['number'] == '100.1a')
    assert {'name': 'Flying', 'number': '702.9'} in keywords


def test_local_search_numbers_text_and_snapshot_versions(tmp_path):
    store = RulesStore(tmp_path / 'rules.sqlite')
    assert store.index() == {'metadata': None, 'sections': [], 'keywords': []}
    first = store.install(DOCUMENT, 'local fixture')
    assert [row['number'] for row in store.search('rule 702.9')] == ['702.9', '702.9a', '702.9b']
    assert store.search('702.9a')[0]['number'] == '702.9a'
    assert all('flying' in row['body'].casefold() for row in store.search('flying'))
    assert store.search('flying individual') == []
    assert store.search('" OR * --') == []
    assert len(store.search('', limit=2)) == 2
    assert store.search('100')[0]['number'] == '100'
    partial = store.search('70')
    assert partial and all(row['number'].startswith('70') for row in partial)
    assert [row['number'] for row in store.search('rule 70')] == [row['number'] for row in partial]
    newer = DOCUMENT.replace('September 25', 'October 23')
    second = store.install(newer, 'new fixture')
    assert second['metadata']['effective_date'] == '2026-10-23'
    assert first['metadata']['checksum'] != second['metadata']['checksum']
    assert RulesStore(store.path).index() == second
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 2


def test_bad_or_older_updates_preserve_installed_snapshot(tmp_path):
    store = RulesStore(tmp_path / 'rules.sqlite')
    installed = store.install(DOCUMENT, 'known good')
    with pytest.raises(ValueError, match='incomplete'):
        store.install(DOCUMENT.split('Glossary\nFlying')[0], 'truncated')
    with pytest.raises(ValueError, match='older'):
        store.install(DOCUMENT.replace('September 25', 'September 24'), 'old')
    assert store.index() == installed
    with store.connect() as db:
        db.execute('''CREATE TRIGGER reject_install BEFORE INSERT ON rules
            WHEN NEW.number='903.1' BEGIN SELECT RAISE(ABORT, 'simulated failure'); END''')
    with pytest.raises(sqlite3.IntegrityError, match='simulated failure'):
        store.install(DOCUMENT.replace('September 25', 'October 23'), 'failed transaction')
    assert store.index() == installed


def test_future_format_is_not_modified(tmp_path):
    path = tmp_path / 'future.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='Unsupported'):
        RulesStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 99


def test_service_reads_are_offline_and_refresh_discovers_current_official_link(tmp_path):
    source = 'https://media.wizards.com/2026/downloads/MagicCompRules%2020260925.txt'
    calls = []
    def fetch(url):
        calls.append(url)
        if url == RULES_PAGE:
            return ('<a href="https://example.com/MagicCompRules.txt">untrusted</a>'
                    f'<a href="{source.replace("%20", " ")}">TXT</a>').encode()
        assert url == source
        return DOCUMENT.encode()
    service = CardService(db_path=str(tmp_path / 'cards.sqlite'), fetch_bytes_fn=fetch)
    assert service.rules_index()['metadata'] is None
    assert service.search_rules('Flying') == []
    assert calls == []
    installed = service.refresh_rules()
    assert calls == [RULES_PAGE, source]
    assert installed['metadata']['source'] == source
    assert service.search_rules('Flying')
    assert calls == [RULES_PAGE, source]
    original = deepcopy(installed)
    service.fetch_bytes_fn = lambda url: b'<html>No supported download</html>'
    with pytest.raises(ValueError, match='No official'):
        service.refresh_rules()
    assert service.rules_index() == original


def test_import_local_file_without_network(tmp_path):
    path = tmp_path / 'rules.txt'
    path.write_text(DOCUMENT, encoding='utf-8-sig')
    def no_network(url):
        pytest.fail('Local imports must not download rules')
    service = CardService(db_path=str(tmp_path / 'cards.sqlite'), fetch_bytes_fn=no_network)
    assert service.import_rules(path)['metadata']['effective_date'] == '2026-09-25'
