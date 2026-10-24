from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.sections import DeckSection
from mtg_editor.organization import in_deck_entries
from mtg_editor.recommendation_pages import RecommendationPages


def test_ranked_pages_pass_two_hundred_and_filter_before_slicing():
    pages = RecommendationPages()
    for start in range(0, 275, 50):
        pages.append([dict(oracle_id=f'oracle-{index:03}', score=1000-index,
                           entry=DeckEntry(str(index), f'Card {index:03}', card_id=f'print-{index}',
                                           oracle_id=f'oracle-{index:03}',
                                           extras={'facts': {'type_line': 'Artifact' if index % 10 == 0 else 'Creature'}}),
                           roles=[{'name': 'Ramp' if index % 2 == 0 else 'Draw'}])
                      for index in range(start, min(start+50, 275))])
    document = DeckDocument()
    rows, more = pages.page(document)
    assert len(rows) == 50 and more
    rows, more = pages.page(document, limit=250)
    assert len(rows) == 250 and more
    assert [row['oracle_id'] for row in rows] == [f'oracle-{index:03}' for index in range(250)]
    rows, more = pages.page(document, limit=300)
    assert len(rows) == 275 and not more
    document.deck.entries = [DeckEntry('owned', 'Card 000', oracle_id='oracle-000', section=DeckSection.EXCLUDED)]
    rows, more = pages.page(document, kind='Artifact', role='Ramp')
    assert len(rows) == 27 and not more
    assert rows[0]['oracle_id'] == 'oracle-010'
    rows, more = pages.page(document, membership=2)
    assert [row['oracle_id'] for row in rows] == ['oracle-000']
    rows, more = pages.page(document, text='Card 27', dismissed=['oracle-270'])
    assert [row['oracle_id'] for row in rows] == [f'oracle-{index}' for index in range(271, 275)]


def test_membership_uses_all_sections_and_respects_reliable_oracle_identity():
    document = DeckDocument()
    document.deck.entries = [DeckEntry(str(index), 'Same Name', oracle_id=f'owned-{index}', section=section)
                             for index, section in enumerate(DeckSection)]
    candidates = [DeckEntry(str(index), 'Alternate printing', card_id=f'alt-{index}', oracle_id=f'owned-{index}')
                  for index, _ in enumerate(DeckSection)]
    candidates.append(DeckEntry('unrelated', 'Same Name', oracle_id='unrelated'))
    assert in_deck_entries(document, candidates) == {entry.entry_id for entry in candidates[:-1]}
    document.deck.entries.append(DeckEntry('legacy', '  Legacy   Card '))
    candidates.append(DeckEntry('legacy-match', 'legacy card', oracle_id='new-oracle'))
    assert 'legacy-match' in in_deck_entries(document, candidates)
