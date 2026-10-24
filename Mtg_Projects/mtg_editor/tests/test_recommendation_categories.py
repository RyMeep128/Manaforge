from datetime import date, timedelta

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.recommendation_categories import categories
from mtg_editor.recommendation_pages import RecommendationPages


def candidate(number, line, text='', **facts):
    return dict(oracle_id=f'o{number}', score=100-number, roles=[],
                entry=DeckEntry(f'e{number}', f'Card {number}', oracle_id=f'o{number}',
                                extras={'facts': dict(type_line=line, oracle_text=text, **facts)}))


def test_functional_categories_and_release_metadata():
    mana = candidate(1, 'Artifact', '{T}: Add {G}.', released_at=date.today().isoformat())
    utility = candidate(2, 'Artifact', '{T}: Draw a card.')
    land = candidate(3, 'Land', '{T}: Add {U}.')
    assert {'Top Cards', 'Mana Artifacts', 'New Cards'} <= categories(mana)
    assert 'Utility Artifacts' not in categories(mana)
    assert 'Utility Artifacts' in categories(utility)
    assert 'Utility Lands' not in categories(land)
    land['entry'].extras['facts']['oracle_text'] += '\n{2}, {T}: Draw a card.'
    assert {'Lands', 'Utility Lands'} <= categories(land)
    mana['entry'].extras['facts']['released_at'] = (date.today() + timedelta(days=30)).isoformat()
    assert 'New Cards' not in categories(mana)


def test_high_lift_requires_same_source_baseline():
    row = candidate(1, 'Creature')
    row['source_evidence'] = {'edhrec': dict(synergy=0.9, sample=100)}
    assert 'High Lift' not in categories(row)
    row['source_evidence']['archidekt'] = dict(inclusion=0.5, baseline=0.1, sample=20)
    assert 'High Lift' in categories(row)
    row['source_evidence']['archidekt']['baseline'] = 0
    assert 'High Lift' not in categories(row)


def test_category_filters_before_pagination_and_excludes_alternate_printings():
    pages = RecommendationPages()
    rows = [candidate(i, 'Creature' if i % 2 else 'Instant', color_identity=['W'], cmc=2)
            for i in range(130)]
    pages.append(rows)
    document = DeckDocument()
    document.deck.entries = [DeckEntry('existing', 'Alternate art', oracle_id='o1')]
    first, more = pages.page(document, category='Creatures', identity='W', mana_value=2)
    assert len(first) == 50 and more
    assert first[0]['oracle_id'] == 'o3'
    assert all('Creatures' in categories(row) for row in first)
    all_rows, more = pages.page(document, category='Creatures', limit=100)
    assert len(all_rows) == 64 and not more
    assert not pages.page(document, category='Creatures', identity='U')[0]
