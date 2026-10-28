"""Commander/deck regression cases, run by CI (no network fixtures)."""
from mtg_core.categorization import classify, refresh_automatic_categories
from mtg_core.decks import DeckCategory, DeckDocument, DeckEntry
from mtg_core.role_analysis import deck_context


def card(kind='Creature', text='', keywords=()):
    return dict(type_line=kind, oracle_text=text, keywords=list(keywords))


def roles(payload, context):
    return [m['name'] for m in classify(payload, context=context)]


def test_tribal_deck_without_tribal_commander_retains_mana_role():
    elves = [card('Creature \u2014 Elf Druid', '{T}: Add {G}.') for _ in range(8)]
    context = deck_context(elves)
    assert context['_strategy']['tribes'] == ['druid', 'elf']
    assert roles(elves[0], context)[0] == 'Ramp'
    assert 'Tribal' in roles(elves[0], context)
    assert 'Tribal' in roles(card('Creature \u2014 Shapeshifter', 'Changeling'), context)


def test_commander_enchantment_and_goad_themes_coexist():
    commander = card(text='Whenever an enchantment enters under your control, goad target creature.')
    aura = card('Enchantment \u2014 Aura', 'Enchant creature. Enchanted creature gets +2/+2.')
    payloads = [commander, aura, card(text='Goad target creature.'),
                card(text='Whenever an enchantment enters, draw a card.')]
    context = deck_context(payloads, [commander])
    assert {'Goad', 'Enchantment Matters'} <= set(context['_strategy']['themes'])
    assert 'Enchantment Matters' in roles(aura, context)
    assert 'Goad' not in roles(aura, context)


def test_incidental_single_type_does_not_create_theme():
    context = deck_context([card('Artifact Creature \u2014 Golem')])
    assert context['_strategy']['themes'] == []
    assert context['_strategy']['tribes'] == []


def test_manual_membership_survives_refresh_and_unused_auto_categories_disappear():
    doc = DeckDocument()
    manual = DeckEntry('manual', 'Manual', category_ids=['custom'],
                       extras={'facts': card(text='Goad target creature.')})
    automatic = DeckEntry('auto', 'Automatic', extras={'facts': card(text='Goad target creature.')})
    doc.deck.entries = [manual, automatic]
    doc.deck.categories = [DeckCategory('custom', 'My cards')]
    refresh_automatic_categories(doc)
    assert manual.category_ids == ['custom']
    assert 'auto:goad' in automatic.category_ids
    automatic.extras['facts'] = card(text='Draw two cards.')
    refresh_automatic_categories(doc)
    assert automatic.category_ids[0] == 'auto:draw'
    assert all(c.category_id != 'auto:goad' for c in doc.deck.categories)
    assert manual.category_ids == ['custom']


def test_costs_and_self_protection_do_not_displace_mana_generation():
    payload = card('Creature \u2014 Elf', 'Hexproof. {T}: Add {G}.', ['Hexproof'])
    assert roles(payload, deck_context([payload]))[0] == 'Ramp'


def test_generated_effect_cache_uses_exact_facts_and_returns_fresh_evidence(monkeypatch):
    import mtg_core.role_analysis as analysis
    payload = card('Artifact', '{T}: Add {C}{C}.')
    key, evidence = analysis.effect_cache_record(payload)
    monkeypatch.setattr(analysis, 'generated_effects', lambda: {key: evidence})
    def unexpected_parse(_):
        raise AssertionError('Matching generated evidence should skip Oracle parsing')
    monkeypatch.setattr(analysis, '_analyze_cached', unexpected_parse)
    first = analysis.analyze_effects(payload)
    first['Ramp']['reasons'].append('Caller mutation')
    assert 'Caller mutation' not in analysis.analyze_effects(payload)['Ramp']['reasons']
