"""CI-only preview contract/lifecycle tests: no engine, editor or private user data."""

from copy import deepcopy
import json
from pathlib import Path
import threading
import pytest
from PyQt6.QtGui import QImage
from mtg_core.decks import Deck, DeckDocument, DeckEntry
from mtg_play import deck_preview as module
from mtg_play.deck_preview import (
    PreviewError,
    PreviewLaunch,
    project_deck,
    prepare_preview,
    run_preview,
)
from mtg_play.launch_lifecycle import LaunchOwner, LaunchState
from mtg_play.tests.test_visual_catalog import Service, card


def document():
    return DeckDocument(
        deck=Deck(
            name="Public test deck",
            entries=[
                DeckEntry("a", "Card", 3, card_id="selected", oracle_id="oracle"),
                DeckEntry("b", "Card", 2, card_id="selected", oracle_id="oracle"),
            ],
        )
    )


@pytest.mark.parametrize("format", ["freeform", "commander"])
def test_projection_preserves_duplicates_quantities_format_and_source(format):
    source = document()
    before = deepcopy(source.to_dict())
    value = project_deck(
        source, format, Service(card("selected", type_line="Creature", mana_cost="{G}"))
    )
    assert value["format"] == format and value["mode"] == "deck_preview"
    assert [r["quantity"] for r in value["cards"]] == [3, 2]
    assert [r["entry_id"] for r in value["cards"]] == ["a", "b"]
    assert all(
        r["printing_id"] == "selected" and r["oracle_id"] == "oracle"
        for r in value["cards"]
    )
    assert (
        source.to_dict() == before
        and "seats" not in value
        and "legal_actions" not in value
    )


def test_projection_is_bounded_and_does_not_invent_unresolved_printing():
    source = document()
    source.deck.entries = [DeckEntry(str(i), "Missing", 1) for i in range(30)]
    value = project_deck(source, "freeform", Service(card("other")))
    assert len(value["cards"]) == 24 and value["total_entries"] == 30
    assert all(
        row["printing_id"] is None and row["rules_text"] is None
        for row in value["cards"]
    )


@pytest.mark.parametrize("mutation", ["duplicate", "quantity", "empty"])
def test_invalid_source_is_rejected(mutation):
    source = document()
    if mutation == "duplicate":
        source.deck.entries[1].entry_id = "a"
    elif mutation == "quantity":
        source.deck.entries[0].quantity = True
    else:
        source.deck.entries = []
    with pytest.raises(PreviewError):
        project_deck(source, "freeform", Service(card("selected")))


def test_preparation_pins_files_and_missing_art_without_network(tmp_path):
    source = document()
    service = Service(card("selected", type_line="Creature"))
    startup = json.loads(prepare_preview(source, "commander", service, tmp_path))
    import hashlib

    assert (
        startup["deck_sha256"]
        == hashlib.sha256((tmp_path / "deck.json").read_bytes()).hexdigest()
    )
    art = json.loads((tmp_path / "artwork/manifest.json").read_text())
    assert art["entries"] == [] and art["unavailable"][0]["code"] == "ARTWORK_MISSING"
    assert "cards" not in startup and "viewer_key" not in startup
    assert all(call[0] != "download" for call in service.calls)


def test_special_printing_is_exported_authentically_without_reconstruction(tmp_path):
    image = QImage(4, 6, QImage.Format.Format_RGBA8888)
    image.fill(0xFF008000)
    path = tmp_path / "source.png"
    assert image.save(str(path))
    root = tmp_path / "preview"
    root.mkdir()
    payload = card("selected", type_line="Creature")
    payload["full_art"] = True
    prepare_preview(
        document(),
        "freeform",
        Service(payload, paths={("selected", "default"): path}),
        root,
    )
    art = json.loads((root / "artwork/manifest.json").read_text())
    assert (
        art["entries"][0]["printing_id"] == "selected"
        and art["entries"][0]["standard_compatible"] is False
    )


class Child:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


def fake_owner(monkeypatch):
    from mtg_play import launch_lifecycle

    child = Child()
    commands = []
    monkeypatch.setattr(
        launch_lifecycle.subprocess,
        "Popen",
        lambda command, **kw: commands.append((command, kw)) or child,
    )
    monkeypatch.setattr(
        launch_lifecycle,
        "stop_process",
        lambda p: dict(exit_code=p.code, reaped=True, forced=False),
    )
    owner = LaunchOwner()
    monkeypatch.setattr(owner, "_write_client_bootstrap", lambda *args: None)
    return owner, child, commands


def test_preview_child_never_fakes_a_gateway_and_owns_cleanup(monkeypatch):
    owner, child, commands = fake_owner(monkeypatch)
    owner.start_preview(["public-player"], preview_bootstrap=b"{}")
    assert owner.state == LaunchState.STARTING_CLIENT
    owner.client_ready()
    child.code = 0
    assert owner.client_exit_code == 0 and owner.close().confirmed
    assert [x.role for x in owner.report.children] == ["client"]
    assert commands[0][1]["shell"] is False


@pytest.mark.parametrize("cancelled", [False, True])
def test_launch_failure_or_cancel_cleans_owned_assets(monkeypatch, tmp_path, cancelled):
    owner, child, commands = fake_owner(monkeypatch)
    launch = PreviewLaunch(owner)
    player = tmp_path / "player.exe"
    player.write_bytes(b"public-stub")
    monkeypatch.setattr(module, "prepare_preview", lambda *a: b"{}")
    cancel = threading.Event()
    if cancelled:
        cancel.set()
    else:
        child.code = 3
    if cancelled:
        assert (
            run_preview(
                document(),
                "freeform",
                None,
                cancel,
                lambda x: None,
                player=player,
                launch=launch,
            )
            == "cancelled"
        )
    else:
        with pytest.raises(Exception):
            run_preview(
                document(),
                "freeform",
                None,
                cancel,
                lambda x: None,
                player=player,
                launch=launch,
            )
    assert launch.root is None and owner.close().confirmed


def test_missing_build_does_not_create_a_workspace(tmp_path):
    launch = PreviewLaunch()
    with pytest.raises(PreviewError, match="PREVIEW_BUILD_MISSING"):
        run_preview(
            document(),
            "freeform",
            None,
            threading.Event(),
            lambda x: None,
            player=tmp_path / "missing",
            launch=launch,
        )
    assert launch.root is None


def test_cleanup_failure_retains_ownership_and_allows_retry(monkeypatch):
    import tempfile

    owner, child, commands = fake_owner(monkeypatch)
    launch = PreviewLaunch(owner)
    launch.root = Path(tempfile.mkdtemp(prefix="manaforge-deck-preview-"))
    root = launch.root
    original = module.shutil.rmtree
    monkeypatch.setattr(
        module.shutil, "rmtree", lambda p: (_ for _ in ()).throw(OSError())
    )
    with pytest.raises(PreviewError, match="PREVIEW_FILES_CLEANUP_FAILED"):
        launch.close()
    assert launch.root == root and root.exists()
    monkeypatch.setattr(module.shutil, "rmtree", original)
    launch.close()
    assert launch.root is None and not root.exists()


def test_shared_fixture_is_an_actual_native_document_projection():
    source = DeckDocument(
        deck=Deck(
            name="Public test deck",
            entries=[
                DeckEntry(
                    "public-entry",
                    "Public card",
                    3,
                    card_id="public-printing",
                    oracle_id="public-oracle",
                )
            ],
        )
    )
    metadata = card(
        "public-printing",
        type_line="Creature",
        mana_cost="{G}",
        power="2",
        toughness="2",
    )
    metadata.update(name="Public card", oracle_id="public-oracle")
    expected = json.loads(
        (
            Path(module.__file__).parent / "protocol/fixtures/deck-preview-v1.json"
        ).read_text()
    )
    assert project_deck(source, "freeform", Service(metadata)) == expected


def test_repeated_owned_child_and_cancel_never_require_java(tmp_path):
    import sys

    for _ in range(3):
        owner = LaunchOwner()
        owner.start_preview(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
            preview_bootstrap=b"{}",
            cwd=str(tmp_path),
        )
        assert owner.client_exit_code is None
        owner.request_cancel()
        assert owner.close().confirmed and owner.report.runtime_confirmed


def test_preview_can_render_cached_standard_without_changing_selected_identity(
    tmp_path,
):
    image = QImage(4, 6, QImage.Format.Format_RGBA8888)
    image.fill(0xFF008000)
    path = tmp_path / "standard.png"
    assert image.save(str(path))
    selected = card("selected", type_line="Creature")
    selected["full_art"] = True
    service = Service(
        selected,
        [card("standard", type_line="Creature")],
        {("standard", "default"): path},
    )
    # Service in production resolves each printing independently.
    service.get_card = lambda *, card_id: (
        selected if card_id == "selected" else card("standard", type_line="Creature")
    )
    root = tmp_path / "preview"
    root.mkdir()
    prepare_preview(document(), "freeform", service, root)
    data = json.loads((root / "deck.json").read_text())
    assert all(
        row["printing_id"] == "selected" and row["artwork_printing_id"] == "standard"
        for row in data["cards"]
    )
