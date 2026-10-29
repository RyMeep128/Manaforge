"""Offline catalog workspace contracts, collected by the existing Core CI suite."""

import threading
from types import SimpleNamespace

import pytest

from mtg_core.catalog_workspace import CatalogWorkspace, artwork_faces, missing_artwork
from mtg_core.downloads import DownloadCancelled
from mtg_core.services import CardService


@pytest.fixture
def catalog(tmp_path):
    def offline(*args, **kwargs):
        pytest.fail("Browsing must never contact a remote service")

    service = CardService(
        db_path=str(tmp_path / "cards.sqlite3"),
        image_root=str(tmp_path / "images"),
        fetch_json_fn=offline,
        fetch_bytes_fn=offline,
    )
    for number in range(3):
        service.database.upsert_card_payload(
            dict(
                id=f"print-{number}",
                oracle_id="oracle",
                name="Local Bird",
                set="tst",
                set_name="Test Set",
                collector_number=str(number),
                type_line="Creature — Bird",
                oracle_text="Draw a card.",
                cmc=2,
                colors=["U"],
                color_identity=["U"],
                rarity="rare",
                legalities={"commander": "legal"},
                lang="en",
                image_uris={"png": "https://cards.scryfall.io/example.png"},
            )
        )
    return CatalogWorkspace(service)


def test_unique_and_printing_modes_share_local_filters(catalog):
    cancel = threading.Event()
    query = "o:draw t:bird c:u id:u mv:2 r:rare f:commander"
    unique, _, more = catalog.page(query, cancel=cancel)
    prints, _, _ = catalog.page(query, unique=False, cancel=cancel)
    assert len(unique) == 1
    assert len(prints) == 3
    assert not more
    assert catalog.page("cn:1", unique=False, cancel=cancel)[0][0].card_id == "print-1"
    assert len(catalog.page(set_filter="Test Set", unique=False, cancel=cancel)[0]) == 3
    assert catalog.page("not-present", cancel=cancel)[0] == []


def test_pagination_has_no_duplicates_and_preserves_oracle_scope(catalog):
    catalog.PAGE_SIZE = 2
    cancel = threading.Event()
    first, cursor, more = catalog.page(unique=False, cancel=cancel)
    second, _, more2 = catalog.page(unique=False, offset=cursor, cancel=cancel)
    assert more and not more2
    assert len({r.card_id for r in first + second}) == 3
    assert catalog.page(oracle_ids=["other"], unique=False, cancel=cancel)[0] == []


def test_missing_artwork_checks_each_image_bearing_face():
    payload = dict(
        card_faces=[{"image_uris": {"png": "front"}}, {"image_uris": {"png": "back"}}]
    )
    row = SimpleNamespace(card_id="dfc", payload=payload)
    paths = {"default": "front.png"}
    service = SimpleNamespace(get_image_path=lambda card, variant: paths.get(variant))
    assert artwork_faces(payload) == [0, 1]
    assert missing_artwork(service, row)
    paths["face-1"] = "back.png"
    assert not missing_artwork(service, row)
    assert artwork_faces(
        {
            "card_faces": [{"name": "Left"}, {"name": "Right"}],
            "image_uris": {"png": "combined"},
        }
    ) == [0]


def test_selection_download_does_not_expand_scope_and_honors_cancellation(catalog):
    rows = catalog.page(unique=False, cancel=threading.Event())[0]
    calls = []
    catalog.service.cache_artwork = lambda card, face, **kwargs: calls.append(
        (card, face)
    )
    catalog.download(rows[:1], cancel=threading.Event(), report=lambda value: None)
    assert calls == [(rows[0].card_id, 0)]
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(DownloadCancelled):
        catalog.download(rows, cancel=cancelled, report=lambda value: None)
    assert len(calls) == 1


def test_failed_face_does_not_skip_other_selected_printings(catalog):
    rows = catalog.page(unique=False, cancel=threading.Event())[0]
    calls = []

    def download(card, face, **kwargs):
        calls.append(card)
        if card == rows[0].card_id:
            raise OSError("Unavailable")

    catalog.service.cache_artwork = download
    with pytest.raises(ValueError, match="Unavailable"):
        catalog.download(rows, cancel=threading.Event(), report=lambda value: None)
    assert calls == [r.card_id for r in rows]
