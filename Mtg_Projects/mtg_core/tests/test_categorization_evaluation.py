"""Small held-out strategy regressions; these are not a population accuracy claim."""
import json
import os
from pathlib import Path
import uuid

from mtg_core.categorization_evaluation import evaluate
from mtg_core.decks import DeckDocument, DeckEntry


# Authored independently of the precon corpus. Labels are explicit, never inferred
# from whether the classifier happened to choose a specialized category.
CASES = [
    ('Tribal', 'Creature — Elf Druid', '{T}: Add {G}.', 'Ramp'),
    ('Aristocrats', 'Instant', 'Draw two cards.', 'Draw'),
    ('Tokens', 'Sorcery', 'Destroy target creature.', 'Removal'),
    ('Enchantments', 'Enchantment — Aura', 'Enchanted creature has indestructible.', 'Protection'),
    ('Artifacts', 'Artifact', '{T}: Add {C}.', 'Ramp'),
    ('Spellslinger', 'Instant', 'Counter target spell.', 'Counterspells'),
    ('Landfall', 'Sorcery', 'Draw two cards.', 'Draw'),
    ('Voltron', 'Instant', 'Target creature gains indestructible until end of turn.', 'Protection'),
    ('Graveyard', 'Sorcery', 'Return target creature card from your graveyard to your hand.', 'Recursion'),
    ('Mixed', 'Instant', 'Destroy target creature.', 'Removal'),
]


def test_paired_held_out_strategy_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv('PRINT_PROXY_PREP_DATA_DIR', str(tmp_path))
    samples = []
    community = {}
    for index, (strategy, kind, text, expected) in enumerate(CASES):
        document = DeckDocument()
        oracle = str(uuid.UUID(int=index + 100))
        document.editor_preferences['manual_themes'] = [{'slug': strategy.lower(), 'roles': []}]
        document.deck.entries = [DeckEntry('role', strategy + ' functional sample', oracle_id=oracle, extras={'facts':
            {'type_line': kind, 'oracle_text': text}}),
            DeckEntry('generic', 'Generic sample', extras={'facts': {'type_line': 'Creature — Bear', 'oracle_text': ''}})]
        samples.append({'strategy': strategy, 'document': document.to_dict(), 'labels': {
            'role': {'acceptable': [expected], 'kind': 'functional'},
            'generic': {'acceptable': ['Creatures'], 'kind': 'context'}}})
        # Deliberately contradictory independent evidence tests resistance to
        # theme popularity. It is not derived from the expected labels.
        community[oracle] = [dict(author=f'person-{i}', deck=f'list-{i}', category='Tokens',
            commanders=[], themes=['theme:' + strategy.lower()], format=document.deck.format) for i in range(3)]
    report = evaluate(samples, community)
    for mode in ('baseline', 'community'):
        assert report[mode]['cards'] == 20
        assert report[mode]['functional_correct'] == 10
        assert report[mode]['generic_fallbacks'] == 10
        assert len(report[mode]['strategies']) == 10
    # Verify the metric counts real errors and penalizes an incorrect specific role.
    samples[0]['labels']['role']['acceptable'] = ['Draw']
    errors = evaluate(samples)['baseline']
    assert errors['correct'] == 19
    assert errors['incorrect_specialized'] == 1
    output = os.environ.get('MANAFORGE_CATEGORY_EVALUATION')
    if output:
        Path(output).write_text(json.dumps(report, indent=2), encoding='utf-8')


def test_explicit_typal_theme_classifies_only_supporting_cards(tmp_path, monkeypatch):
    from mtg_core.categorization import refresh_automatic_categories
    monkeypatch.setenv('PRINT_PROXY_PREP_DATA_DIR', str(tmp_path))
    doc = DeckDocument()
    doc.editor_preferences['manual_themes'] = [{'slug': 'elves', 'subtype': 'Elf', 'roles': []}]
    doc.deck.entries = [DeckEntry('elf', 'Elf', extras={'facts': {'type_line': 'Creature — Elf'}}),
        DeckEntry('ramp', 'Mana Elf', extras={'facts': {'type_line': 'Creature — Elf Druid', 'oracle_text': '{T}: Add {G}.'}}),
        DeckEntry('bear', 'Bear', extras={'facts': {'type_line': 'Creature — Bear'}})]
    refresh_automatic_categories(doc)
    assert [e.category_ids[0] for e in doc.deck.entries] == ['auto:tribal', 'auto:ramp', 'auto:creatures']
