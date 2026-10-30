"""Frozen artwork preparation and network-denied image reads for CI."""

from copy import deepcopy
from threading import Event
import socket
import urllib.request

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.assets import prepare_assets
from mtg_play.artwork_cache import read_local_image, RENDER_VERSION
from mtg_play.tests.test_artwork_cache import LocalOnlyService, source


def document(*entries):
    result = DeckDocument()
    result.deck.entries = list(entries)
    return result


def test_fully_cached_preparation_generates_shared_crops_and_freezes_sources(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path / "data"))
    path = source(tmp_path / "printing.png")
    service = LocalOnlyService({("print", "default"): path}, layout="normal")
    deck = document(DeckEntry("one", "Forest", 60, card_id="print"))
    before = deepcopy(deck.to_dict())
    progress = []
    assets = prepare_assets(
        (deck, deck), service, cancel=Event(), report=progress.append
    )
    assert not assets.missing and len(assets.sources) == 1
    assert list((tmp_path / "data").rglob("*.png"))
    assert deck.to_dict() == before and progress[-1]["current"] == 2
    frozen = assets.image_service()
    assert frozen.get_image_path("print") == str(path.resolve())
    assert frozen.get_image_path("engine-generated-token") is None
    source(path, top="blue")
    assert frozen.get_image_path("print") is None


def test_missing_front_and_back_are_reported_without_excluded_cards(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path / "data"))
    path = source(tmp_path / "front.png")
    service = LocalOnlyService({("dfc", "default"): path}, layout="transform")
    deck = document(
        DeckEntry("one", "Transform card", card_id="dfc"),
        DeckEntry("two", "Missing card", card_id="missing", section="sideboard"),
        DeckEntry("three", "No printing"),
        DeckEntry("four", "Another no printing"),
        DeckEntry("five", "Excluded", section="excluded"),
    )
    assets = prepare_assets((deck,), service, cancel=Event(), report=lambda v: None)
    assert set(assets.missing) == {
        "Transform card (alternate face)",
        "Missing card",
        "Missing card (alternate face)",
        "No printing",
        "Another no printing",
    }
    assert assets.image_service().get_image_path("dfc", "face-1") is None


def test_frozen_gameplay_crop_and_inspection_are_network_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path / "data"))
    path = source(tmp_path / "front.png")
    back = source(tmp_path / "back.png", top="blue")
    service = LocalOnlyService({("dfc", "default"): path, ("dfc", "face-1"): back})
    assets = prepare_assets(
        (document(DeckEntry("one", "Face card", card_id="dfc")),),
        service,
        cancel=Event(),
        report=lambda v: None,
    )
    assert not assets.missing

    def forbidden(*args, **kwargs):
        raise AssertionError("Network/live catalog access during gameplay")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    service.get_image_path = service.get_card = forbidden
    frozen = assets.image_service()
    for face in (0, 1):
        assert not read_local_image(
            frozen, ("dfc", None, 300, face, RENDER_VERSION)
        ).isNull()
        assert not read_local_image(frozen, ("dfc", None, 600, face)).isNull()
    assert read_local_image(frozen, ("new-token", None, 600, 0)).isNull()


def test_cancelled_preparation_returns_no_manifest():
    cancel = Event()
    cancel.set()
    deck = document(DeckEntry("one", "Forest", card_id="print"))
    assert (
        prepare_assets((deck,), object(), cancel=cancel, report=lambda v: None) is None
    )


def test_all_display_commanders_are_omitted_from_asset_requirements():
    deck = document(
        DeckEntry("land", "Forest"),
        DeckEntry("display-a", "First display commander", section="display_commander"),
        DeckEntry(
            "display-b",
            "Different display commander",
            section="display_commander",
            card_id="unknown",
        ),
    )
    before = deepcopy(deck.to_dict())
    assets = prepare_assets(
        (deck,), object(), cancel=Event(), report=lambda value: None
    )
    assert assets.missing == ("Forest",)
    assert not assets.sources and deck.to_dict() == before
