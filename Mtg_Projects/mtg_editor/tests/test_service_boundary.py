from PyQt6 import QtWidgets as W

from mtg_core.decks import DeckEntry
from mtg_editor.gui import EditorWindow


def test_editor_actions_use_service_without_database_access(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    calls = []

    class Service:
        @property
        def database(self):
            raise AssertionError('Editor must not access persistence')

        def analyze_entries(self, entries):
            calls.append(('analysis', [e.entry_id for e in entries]))
            return {}

        def get_deck_legality_data(self, entries):
            calls.append(('legality', [e.card_id for e in entries]))
            return {}

        def get_oracle_tags(self, oracle_id):
            calls.append(('tags', oracle_id))
            return []

    window = EditorWindow(service=Service(), root=tmp_path)
    entry = DeckEntry('entry', 'Card', card_id='card', oracle_id='oracle')
    window.document.deck.entries = [entry]
    # Run only the queued work; review dialogs are tested separately.
    window.run_task = lambda work, callback: work()
    window.auto_categorize()
    window.commander_checks()
    window.view_tags(entry)
    window.replace_document(window.document)
    assert calls == [('analysis', ['entry']), ('legality', ['card']),
                     ('tags', 'oracle'), ('analysis', ['entry'])]
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()
