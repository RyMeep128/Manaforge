from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.discovery_themes import theme_catalog
from mtg_core.recommendation_scoring import context, score, DEFAULT_WEIGHTS


def test_explicit_theme_boost_without_commander_keeps_other_candidates():
    doc = DeckDocument()
    doc.editor_preferences['manual_themes'] = [next(
        t for t in theme_catalog([], {}) if t['slug'] == 'artifacts')]
    ctx = context(doc, {})
    def candidate(kind):
        return dict(entry=DeckEntry(kind, kind, extras={'facts': {'type_line': kind}}),
                    roles=[], statistical_score=0.5)
    match = score(candidate('Artifact'), ctx, DEFAULT_WEIGHTS)
    other = score(candidate('Creature'), ctx, DEFAULT_WEIGHTS)
    assert match['score'] > other['score'] > 0
    assert match['components']['themes'] == 2
    assert 'Selected themes: Artifacts' in match['context_reasons']
    inferred = dict(ctx, explicit_themes=[], themes=['Tokens'])
    token = dict(candidate('Creature'), roles=[{'name': 'Tokens'}])
    assert score(token, inferred, DEFAULT_WEIGHTS)['components']['themes'] == 1
