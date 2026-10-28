"""Offline paired evaluation of independently labelled decks, never training data.

Each sample contains a serialized DeckDocument and labels mapping entry IDs to
acceptable primary role names. Labels must be human-reviewed independently of
the classifier. Multiple acceptable roles represent genuine ambiguity.
"""
from time import perf_counter

from .categorization import refresh_automatic_categories, category_key, TYPES
from .decks import DeckDocument


def evaluate(samples, community_records=None):
    results = {}
    generic = {category_key('Sorceries' if t == 'Sorcery' else t + 's') for t in TYPES}
    for mode, records in [('baseline', {}), ('community', community_records or {})]:
        totals = dict(cards=0, correct=0, incorrect_specialized=0, generic_fallbacks=0,
                      functional_cards=0, functional_correct=0, context_cards=0, context_correct=0,
                      manual_preserved=0, manual_cards=0)
        per_strategy = {}
        started = perf_counter()
        for sample in samples:
            document = DeckDocument.from_dict(sample['document'])
            from .categorization import is_manual
            manual = {e.entry_id: e.to_dict() for e in document.deck.entries if is_manual(e)}
            refresh_automatic_categories(document, community_records=records)
            categories = {c.category_id: category_key(c.name) for c in document.deck.categories}
            strategy = per_strategy.setdefault(sample['strategy'], dict(cards=0, correct=0))
            for entry in document.deck.entries:
                if entry.entry_id in manual:
                    totals['manual_cards'] += 1
                    totals['manual_preserved'] += entry.to_dict() == manual[entry.entry_id]
                    continue
                label = sample['labels'].get(entry.entry_id)
                if label is None:
                    continue
                expected = {category_key(role) for role in label['acceptable']}
                predicted = categories.get(entry.category_ids[0], '') if entry.category_ids else ''
                correct = predicted in expected
                totals['cards'] += 1
                totals['correct'] += correct
                totals['generic_fallbacks'] += predicted in generic
                totals['incorrect_specialized'] += bool(predicted) and predicted not in generic and not correct
                group = label.get('kind', 'functional')
                if group in ('functional', 'context'):
                    totals[group + '_cards'] += 1
                    totals[group + '_correct'] += correct
                strategy['cards'] += 1
                strategy['correct'] += correct
        results[mode] = {**totals, 'accuracy': totals['correct'] / totals['cards'] if totals['cards'] else None,
                         'seconds': perf_counter() - started, 'strategies': per_strategy}
    return results
