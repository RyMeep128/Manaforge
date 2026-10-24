from PyQt6.QtWidgets import QApplication, QWidget

from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory
from mtg_editor.recommendations import RecommendationsDialog
import pytest


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


@pytest.mark.parametrize(
    "providers", [("archidekt",), ("edhrec",), ("archidekt", "edhrec")]
)
def test_fused_explanation_preserves_evidence(providers):
    from mtg_editor.recommendations import statistical_reason

    evidence = dict(
        archidekt=dict(
            rank=14, inclusion=0.432, sample=684, baseline=0.081, synergy=0.351
        ),
        edhrec=dict(
            rank=8,
            inclusion=0.518,
            num_decks=1492,
            sample=2881,
            categories=["High Synergy Cards", "Creatures"],
            edhrec_synergy=0.2,
            commanders=["a", "b"],
        ),
    )
    row = dict(
        source_evidence={p: evidence[p] for p in providers},
        public_score=0.86,
        local_relevant=22,
        local_enabled=True,
        commander_names=["Alpha", "Beta"],
        source_status=[
            dict(
                source="other",
                role="public",
                state="unavailable",
                status="No cached data",
            )
        ],
    )
    text = statistical_reason(row)
    for provider in providers:
        assert f"Rank: #{evidence[provider]['rank']}" in text
    if "archidekt" in providers:
        assert "8.1%" in text and "+35.1%" in text
    if "edhrec" in providers:
        assert "1492 / 2881 eligible decks" in text
        assert "High Synergy Cards" in text and "uninterpreted" in text
        assert "Exact cached pair cohort: Alpha + Beta" in text
    assert "No cached data" in text and "80%" in text and "22 relevant decks" in text
    assert "probability" not in text


def test_loader_resolves_bounded_union_offline(monkeypatch):
    from types import SimpleNamespace
    from threading import get_ident
    from mtg_editor.tasks import Task
    from mtg_editor.recommendations import load_recommendations, rank_recommendations
    from mtg_core.recommendation_scoring import settings

    monkeypatch.setattr(
        "socket.socket.connect", lambda *args: pytest.fail("Network access")
    )
    calls = []
    gui_thread = get_ident()

    def printing(oid):
        assert get_ident() != gui_thread
        calls.append(oid)
        return dict(id=oid, name=oid, type_line="Creature", color_identity=[])

    service = SimpleNamespace(
        choose_preferred_print=printing,
        analyze_entries=lambda entries: {},
        get_card=lambda **kwargs: None,
    )

    def source(name):
        return SimpleNamespace(
            source_id=name,
            role="public",
            snapshot=lambda *args, **kwargs: dict(
                results=[
                    dict(oracle_id=f"{name}-{i:04}", score=2000 - i)
                    for i in range(2000)
                ],
                sources=[],
            ),
        )

    document = DeckDocument()
    loaded = []
    worker = Task(
        lambda: loaded.append(
            load_recommendations(
                service, document, None, sources=[source("a"), source("b")]
            )
        )
    )
    worker.start()
    assert worker.wait(5000)
    snapshot = loaded[0]
    assert len(calls) == len(snapshot["results"]) == 200
    assert {r["sources_present"][0] for r in snapshot["results"]} == {"a", "b"}
    assert (
        len(
            rank_recommendations(
                snapshot["results"], snapshot["deck_context"], settings(document)
            )
        )
        == 200
    )


@pytest.mark.parametrize("arch,edh", [(True, True), (True, False), (False, True)])
def test_source_controls_save_independently(tmp_path, monkeypatch, arch, edh):
    from PyQt6 import QtWidgets as W
    from mtg_editor.recommendation_cache import configure_sources
    from mtg_core.recommendation_cache import source_settings

    app = QApplication.instance() or QApplication([])

    class Editor(QWidget):
        def run_task(self, work, callback):
            callback(work())

    def choose(dialog):
        checkboxes = dialog.findChildren(W.QCheckBox)
        checkboxes[0].setChecked(arch)
        checkboxes[1].setChecked(edh)
        dialog.findChild(W.QComboBox).setCurrentIndex(1)
        return W.QDialog.DialogCode.Accepted

    monkeypatch.setattr(W.QDialog, "exec", choose)
    monkeypatch.setattr(W.QMessageBox, "information", lambda *a: None)
    editor = Editor()
    configure_sources(editor, tmp_path)
    config = source_settings(tmp_path)
    assert config["archidekt"] == dict(enabled=arch, cache="portable")
    assert config["edhrec"]["enabled"] == edh
    editor.deleteLater()
    app.processEvents()
