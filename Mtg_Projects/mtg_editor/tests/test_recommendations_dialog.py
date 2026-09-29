from PyQt6.QtWidgets import QApplication, QWidget

from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory
from mtg_editor.recommendations import RecommendationsDialog


def test_edhrec_statistics_are_not_presented_as_global_baseline():
    from mtg_editor.recommendations import statistical_reason

    text = statistical_reason(
        dict(
            statistics_source="edhrec",
            inclusion=0.5,
            num_decks=25,
            sample=50,
            categories=["Top Cards"],
            edhrec_synergy=0.3,
        )
    )
    assert "25 / 50 eligible decks" in text
    assert "uninterpreted" in text
    assert "unavailable" in text
    assert "Global popularity: 0.0%" not in text


def test_preferences_dismissal_and_add_follow_editor_history():
    app = QApplication.instance() or QApplication([])

    class Editor(QWidget):
        def __init__(self):
            super().__init__()
            self.document = DeckDocument()
            self.history = DeckHistory(self.document)

        def edit(self, change):
            self.history.execute(change)

    editor = Editor()
    row = dict(
        oracle_id="candidate",
        entry=DeckEntry("e", "Example", oracle_id="candidate"),
        roles=[],
        score=0.8,
        primary_score=1,
        local_score=0,
        local_enabled=True,
        inclusion=0.5,
        baseline=0.1,
        synergy=0.4,
        sample=20,
        commander="c",
    )
    snapshot = dict(
        results=[row],
        deck_context=dict(gaps={}, themes=[], archetypes=[], average=None, known=0),
        sources=[],
        source="fixture",
        decks=20,
        color_filtered=True,
        source_status=[],
        local_relevant=15,
        local_enabled=True,
        formula="fixture",
    )
    dialog = RecommendationsDialog(snapshot, editor)
    dialog.use_local.setChecked(False)
    assert dialog.rows[0]["score"] == 1
    assert not editor.document.editor_preferences
    dialog.dismiss()
    assert not dialog.rows
    assert editor.document.editor_preferences["recommendations"]["dismissed"] == [
        "candidate"
    ]
    assert editor.history.undo()
    assert not editor.document.editor_preferences
    dialog.restore()
    assert len(dialog.rows) == 1
    dialog.add()
    assert len(editor.document.deck.entries) == 1
    assert editor.history.undo()
    assert not editor.document.deck.entries
    dialog.deleteLater()
    editor.deleteLater()
    app.processEvents()
