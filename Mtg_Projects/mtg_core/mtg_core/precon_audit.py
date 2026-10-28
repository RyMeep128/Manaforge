"""Offline full-catalog categorization audit and compact runtime metadata generator."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import re
from pathlib import Path
import sqlite3

from .categorization import RULE_VERSION, classify
from .role_analysis import deck_context, effect_cache_record, generated_effects
from .paths import core_data_root
from .precons import BUNDLE, load_catalog, normalize_catalog


def run(database, destination):
    # Audit current rules, never replay an earlier generated result.
    generated_effects().clear()
    with gzip.open(BUNDLE, 'rt', encoding='utf-8') as stream:
        catalogs = [json.load(stream)['decks']]
    local = core_data_root() / 'precons.json'
    if local.exists():
        catalogs.append(load_catalog(local))
    cached = core_data_root() / 'recommendations' / 'preconstructed-run' / 'responses'
    for path in sorted(cached.glob('*.gz')):
        with gzip.open(path, 'rt', encoding='utf-8-sig') as stream:
            payload = json.load(stream)
        if isinstance(payload, list) and payload and 'set_code' in payload[0]:
            catalogs.append(normalize_catalog(payload)['decks'])
    decks = {d['id']: d for catalog in catalogs for d in catalog
             if d['format'].casefold() == 'commander'}
    names = {e['name'] for d in decks.values() for e in d['entries']}
    cards, tags = {}, {}
    with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True) as connection:
        for name in sorted(names):
            lookup = re.sub(r' \(Prepared\)$', '', name)
            row = connection.execute(
                'SELECT payload_json FROM prints WHERE lower(name)=lower(?) ORDER BY updated_at DESC, card_id LIMIT 1',
                (lookup,)).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT payload_json FROM prints WHERE name LIKE ? ESCAPE '\\' ORDER BY updated_at DESC, card_id LIMIT 1",
                    (lookup.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + ' // %',)).fetchone()
            if row:
                cards[name] = json.loads(row[0])
        for oid, tag in connection.execute('SELECT oracle_id, tag FROM oracle_tags'):
            tags.setdefault(oid, []).append(tag)
    missing = Counter()
    fallback = Counter()
    reports = []
    total = rows = analyzed = 0
    metadata = {}
    for deck in sorted(decks.values(), key=lambda d: d['id']):
        active = [e for e in deck['entries'] if e['section'] in ('mainboard', 'commander')]
        context = deck_context([cards[e['name']] for e in active if e['name'] in cards],
                               [cards[e['name']] for e in active if e['section'] == 'commander' and e['name'] in cards])
        unresolved = []
        for entry in deck['entries']:
            rows += 1
            total += entry['count']
            payload = cards.get(entry['name'])
            if payload is None:
                missing[entry['name']] += entry['count']
                continue
            analyzed += entry['count']
            evidence = classify(payload, tags.get(payload.get('oracle_id'), []), context)
            if not evidence or all(m['score'] <= 10 for m in evidence):
                fallback[entry['name']] += entry['count']
                unresolved.append(entry['name'])
            # Store only derived roles, never duplicate Oracle text or print data.
            key, effects = effect_cache_record(payload)
            metadata[key] = effects
        reports.append({'id': deck['id'], 'name': deck['name'],
                        'commanders': [e['name'] for e in active if e['section'] == 'commander'],
                        'context': context, 'unresolved': unresolved})
    report = dict(rule_version=RULE_VERSION, decks=len(decks), card_rows=rows,
                  card_copies=total, analyzed_copies=analyzed, unique_cards=len(cards),
                  fallback_copies=sum(fallback.values()), fallback_unique=len(fallback),
                  missing_copies=sum(missing.values()), missing=dict(sorted(missing.items())),
                  unresolved=dict(sorted(fallback.items())), deck_results=reports,
                  catalog_sha256=hashlib.sha256(json.dumps(decks, sort_keys=True).encode()).hexdigest())
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'audit.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    with gzip.GzipFile(filename=str(destination / 'classifications.json.gz'), mode='wb', mtime=0) as stream:
        stream.write(json.dumps({'rule_version': RULE_VERSION, 'cards': metadata}, sort_keys=True, separators=(',', ':')).encode())
    print(json.dumps({k: v for k, v in report.items() if k not in ('deck_results', 'unresolved', 'missing')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=core_data_root() / 'card_data.sqlite3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.database, args.output)


if __name__ == '__main__':
    main()
