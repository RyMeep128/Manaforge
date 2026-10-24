from mtg_core.decks import DeckEntry
from mtg_editor.session import DeckSession


def test_default_name_follows_commander_then_first_added_card_with_undo(tmp_path):
    session = DeckSession(tmp_path)
    session.edit(lambda d: d.deck.entries.append(DeckEntry('first', 'Forest')))
    assert session.document.deck.name == 'Forest'
    session.edit(lambda d: d.deck.entries.append(DeckEntry('commander', 'Lyra', section='commander')))
    assert session.document.deck.name == 'Lyra'
    session.undo()
    assert session.document.deck.name == 'Forest'
    session.redo()
    assert session.document.deck.name == 'Lyra'
    session.edit(lambda d: setattr(d.deck.entries[1], 'section', 'mainboard'))
    assert session.document.deck.name == 'Forest'
    session.edit(lambda d: d.deck.entries.reverse())
    assert session.document.deck.name == 'Forest'
    path = session.save()
    restored = DeckSession(tmp_path)
    restored.open(path)
    assert restored.document.deck.name == 'Forest'


def test_custom_names_are_preserved(tmp_path):
    session = DeckSession(tmp_path)
    session.edit(lambda d: setattr(d.deck, 'name', 'My deck'))
    session.edit(lambda d: d.deck.entries.append(DeckEntry('commander', 'Lyra', section='commander')))
    assert session.document.deck.name == 'My deck'
