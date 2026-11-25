"""Print Set acceptance and regression coverage, run by hosted Python CI."""

import io
import json

import pytest
from PIL import Image

from mtg_core import CardService
from mtg_core.set_catalog import (
    SetInfo,
    discover_sets,
    filter_sets,
    load_set_cards,
    download_set_data,
)
from mtg_print import library, runtime_images
from mtg_print.models import ProjectState
from mtg_print.set_inventory import (
    InventorySettings,
    eligible_cards,
    totals,
    rarity_counts,
)
from mtg_print.services.set_print_service import (
    generate_project,
    SetPrintCancelled,
    SetPrintError,
)


def card(identifier="c", rarity="common", **extra):
    return dict(
        dict(
            id=identifier,
            oracle_id="oracle-" + identifier,
            name="Card " + identifier,
            set="abc",
            set_name="Example Set",
            collector_number=identifier,
            rarity=rarity,
            released_at="2026-01-01",
            lang="en",
            layout="normal",
            type_line="Creature",
            games=["paper"],
            image_uris={"png": "https://example.invalid/" + identifier + ".png"},
        ),
        **extra,
    )


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    service = CardService(
        db_path=str(tmp_path / "catalog.sqlite3"), image_root=str(tmp_path / "art")
    )
    monkeypatch.setattr(library, "cwd", str(tmp_path))
    monkeypatch.setattr(library, "get_default_card_service", lambda: service)
    monkeypatch.setattr(runtime_images, "get_default_card_service", lambda: service)
    return service


def png():
    output = io.BytesIO()
    Image.new("RGB", (63, 88), "blue").save(output, format="PNG")
    return output.getvalue()


def test_set_discovery_counts_oracle_identities_and_searches_codes(catalog):
    for payload in [
        card(),
        card("alt", oracle_id="oracle-c"),
        card("z", set="xyz", set_name="Another Set"),
    ]:
        catalog.database.upsert_card_payload(payload)
    sets, notice = discover_sets(catalog)
    assert notice == ""
    assert filter_sets(sets, "ABC")[0].available == 1
    assert [s.code for s in filter_sets(sets, "another xyz")] == ["xyz"]
    assert filter_sets(sets, "not present") == []
    assert len(load_set_cards(catalog, ["ABC", "abc"])) == 2


def test_remote_directory_keeps_empty_sets_and_local_fallback(catalog):
    catalog.fetch_json_fn = lambda url: {
        "data": [
            dict(
                code="abc",
                name="Example Set",
                card_count=100,
                icon_svg_uri="https://example.invalid/icon.svg",
                released_at="2026-01-01",
            )
        ]
    }
    sets, notice = discover_sets(catalog, online=True)
    assert sets[0].available == 0 and sets[0].expected == 100
    assert sets[0].symbol_url.endswith(".svg")
    catalog.fetch_json_fn = lambda url: (_ for _ in ()).throw(OSError("offline"))
    sets, notice = discover_sets(catalog, online=True)
    assert "unavailable" in notice


def test_download_pages_and_interrupted_data_remains_retryable(catalog):
    pages = [
        {"data": [card()], "has_more": True, "next_page": "next"},
        {"data": [card("u", "uncommon")], "has_more": False},
    ]
    requests = []

    def fetch(url):
        requests.append(url)
        return pages[len(requests) - 1]

    catalog.fetch_json_fn = fetch
    assert download_set_data(catalog, "abc")
    assert len(load_set_cards(catalog, ["abc"])) == 2
    assert requests[1] == "next"
    assert not download_set_data(catalog, "abc", cancelled=lambda: True)
    assert len(load_set_cards(catalog, ["abc"])) == 2


def test_presets_counts_zero_and_individual_overrides():
    cards = [card(), card("u", "uncommon"), card("r", "rare"), card("m", "mythic")]
    settings = InventorySettings()
    assert totals(cards, settings) == (4, 8)
    settings.overrides = {"c": 0, "r": 7}
    assert totals(cards, settings) == (3, 10)
    settings.apply_preset("One of Each")
    assert totals(cards, settings) == (3, 9)
    settings.overrides.clear()
    settings.quantities["common"] = 0
    assert totals(cards, settings) == (3, 3)
    assert rarity_counts(cards)["mythic"] == 1


def test_deduplicates_identity_and_prefers_normal_treatment():
    cards = [
        card(),
        card("alt", oracle_id="oracle-c", full_art=True),
        card("foreign", oracle_id="oracle-c", lang="fr"),
    ]
    settings = InventorySettings()
    assert [c["id"] for c in eligible_cards(cards, settings)] == ["c"]
    settings.alternate_printings = True
    assert len(eligible_cards(cards, settings)) == 3
    cards.append(
        card("french-copy", oracle_id="oracle-c", lang="fr", collector_number="c")
    )
    assert len(eligible_cards(cards, settings)) == 3


def test_related_cards_do_not_duplicate_base_cards_and_favorites_are_respected():
    cards = [
        card(),
        card("bonus", oracle_id="oracle-c", set="bonus", full_art=True),
        card("new", set="bonus"),
    ]
    settings = InventorySettings(related_codes=["bonus"])
    assert totals(eligible_cards(cards, settings), settings) == (2, 8)
    selected = eligible_cards(cards, settings, favorites={"oracle-c": "bonus"})
    assert "bonus" in [c["id"] for c in selected]


def test_name_fallback_lands_tokens_digital_and_unknown_rarity():
    settings = InventorySettings()
    cards = [
        card(oracle_id=None),
        card("legacy", oracle_id=None, name="  CARD   C "),
        card("land", type_line="Basic Snow Land — Plains"),
        card("token", layout="token"),
        card("digital", digital=True),
        card("unknown", rarity="new-rarity"),
    ]
    selected = eligible_cards(cards, settings)
    assert len(selected) == 2
    assert rarity_counts(selected)["other"] == 1
    settings.basic_lands = settings.tokens = True
    assert len(eligible_cards(cards, settings)) == 4


def test_dfc_counts_once_and_split_cards_do_not_need_printed_backs():
    cards = [
        card(
            "dfc", layout="transform", card_faces=[{"name": "Front"}, {"name": "Back"}]
        ),
        card("split", layout="split", card_faces=[{"name": "Left"}, {"name": "Right"}]),
    ]
    settings = InventorySettings()
    assert totals(eligible_cards(cards, settings), settings) == (2, 8)


def test_project_generation_reopens_and_exports_using_normal_pdf(catalog, tmp_path):
    payload = card()
    catalog.database.upsert_card_payload(payload)
    settings = InventorySettings()
    settings.overrides["c"] = 10
    statuses, requests = [], []

    def fetch(url):
        requests.append(url)
        return png()

    entry = generate_project(
        catalog,
        SetInfo("abc", "Example Set"),
        [payload],
        settings,
        defaults={"pagesize": "Letter"},
        fetch_bytes=fetch,
        progress=lambda text, *_: statuses.append(text),
    )
    from mtg_print.services import project_service

    loaded = project_service.load_project_state(entry["path"], {}, lambda _: None)
    assert loaded.loaded_successfully
    state = loaded.state
    assert sum(state.cards.values()) == 10
    assert next(iter(state.card_entries_store.values())).metadata.name == "Card c"
    assert state.set_print_config["overrides"] == {"c": 10}
    assert state.set_print_config["preset"] == "Set Cube"
    assert (
        ProjectState.from_dict(state.to_persisted_dict()).set_print_config
        == state.set_print_config
    )
    copied = ProjectState()
    copied.copy_from(state)
    assert copied.set_print_config == state.set_print_config
    assert entry["display_name"] == "Example Set — Set Cube (4-2-1-1)"
    assert statuses[-1] == "Your project is ready"
    assert len(requests) == 1
    generate_project(
        catalog,
        SetInfo("abc", "Example Set"),
        [payload],
        settings,
        defaults={},
        fetch_bytes=lambda _: pytest.fail("Cached artwork was downloaded again"),
    )
    from services import pdf_service
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtPdf import QPdfDocument

    app = QApplication.instance() or QApplication([])
    state.image_dir = str(tmp_path / "runtime")
    state.img_cache = str(tmp_path / "runtime" / "img.cache")
    path = str(tmp_path / "set.pdf")
    result = pdf_service.generate_pdf(state, (612, 792), path, lambda _: None)
    result.pages.save()
    document = QPdfDocument(app)
    assert document.load(path) == QPdfDocument.Error.None_
    assert document.pageCount() == 2
    assert b"/Subtype /Image" in open(path, "rb").read()
    document.close()


def test_generation_error_and_retry_do_not_publish_partial_project(catalog):
    cards = [card(), card("u", "uncommon")]
    for payload in cards:
        catalog.database.upsert_card_payload(payload)

    def fail_second(url):
        if url.endswith("/u.png"):
            raise OSError("private technical details")
        return png()

    with pytest.raises(SetPrintError, match="Check your connection") as error:
        generate_project(
            catalog,
            SetInfo("abc", "Example"),
            cards,
            InventorySettings(),
            defaults={},
            fetch_bytes=fail_second,
        )
    assert "private technical" not in str(error.value)
    assert library.list_projects() == []
    requests = []
    generate_project(
        catalog,
        SetInfo("abc", "Example"),
        cards,
        InventorySettings(),
        defaults={},
        fetch_bytes=lambda url: (requests.append(url), png())[1],
    )
    assert len(requests) == 1
    assert len(library.list_projects()) == 1


def test_cancellation_preserves_existing_projects(catalog):
    existing = library.create_project("Keep me", prepared_state=ProjectState())
    with pytest.raises(SetPrintCancelled):
        generate_project(
            catalog,
            SetInfo("abc", "Example"),
            [card()],
            InventorySettings(),
            defaults={},
            cancelled=lambda: True,
        )
    assert [entry["id"] for entry in library.list_projects()] == [existing["id"]]


def test_cancel_mid_generation_keeps_cached_work_for_retry(catalog):
    from threading import Event

    stop = Event()
    cards = [card(), card("second")]
    for payload in cards:
        catalog.database.upsert_card_payload(payload)

    def progress(text, value, maximum):
        if text == "Finding card artwork" and value == 1:
            stop.set()

    with pytest.raises(SetPrintCancelled):
        generate_project(
            catalog,
            SetInfo("abc", "Example"),
            cards,
            InventorySettings(),
            defaults={},
            cancelled=stop.is_set,
            progress=progress,
            fetch_bytes=lambda _: png(),
        )
    assert library.list_projects() == []
    assert catalog.get_image_path("c", "default")
    requests = []
    generate_project(
        catalog,
        SetInfo("abc", "Example"),
        cards,
        InventorySettings(),
        defaults={},
        fetch_bytes=lambda url: (requests.append(url), png())[1],
    )
    assert len(requests) == 1


def test_corrupt_artwork_never_publishes_a_successful_project(catalog):
    with pytest.raises(SetPrintError, match="Artwork"):
        generate_project(
            catalog,
            SetInfo("abc", "Example"),
            [card()],
            InventorySettings(),
            defaults={},
            fetch_bytes=lambda _: b"not an image",
        )
    assert library.list_projects() == []
    entry = generate_project(
        catalog,
        SetInfo("abc", "Example"),
        [card()],
        InventorySettings(),
        defaults={},
        fetch_bytes=lambda _: png(),
    )
    assert entry["id"]


def test_missing_metadata_and_artwork_are_explicit(catalog):
    assert eligible_cards([{"id": "broken"}], InventorySettings()) == []
    with pytest.raises(SetPrintError, match="Choose at least one"):
        generate_project(
            catalog, SetInfo("abc", "Example"), [], InventorySettings(), defaults={}
        )
    with pytest.raises(SetPrintError, match="exclude this card"):
        generate_project(
            catalog,
            SetInfo("abc", "Example"),
            [card(image_uris={})],
            InventorySettings(),
            defaults={},
        )
    assert library.list_projects() == []


def test_dfc_prepares_both_faces_and_keeps_quantities(catalog):
    payload = card(
        "dfc",
        layout="transform",
        card_faces=[
            {
                "name": "Front",
                "image_uris": {"png": "https://example.invalid/front.png"},
            },
            {"name": "Back", "image_uris": {"png": "https://example.invalid/back.png"}},
        ],
        image_uris={},
    )
    catalog.database.upsert_card_payload(payload)
    entry = generate_project(
        catalog,
        SetInfo("abc", "Example"),
        [payload],
        InventorySettings(),
        defaults={},
        fetch_bytes=lambda _: png(),
    )
    state = ProjectState.from_dict(
        json.loads(open(entry["path"], encoding="utf-8").read())
    )
    assert sum(state.cards.values()) == 4
    front = next(iter(state.card_entries_store.values()))
    assert front.backside_asset_id and front.backside_name
    assert state.backside_enabled


def test_guided_ui_totals_review_and_incomplete_catalog_guard(catalog, monkeypatch):
    from PyQt6 import QtWidgets as W, QtCore as C
    from mtg_ui.print_set_dialog import PrintSetDialog

    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(PrintSetDialog, "_discover", lambda self: None)
    dialog = PrintSetDialog(service=catalog)
    dialog.sets = [SetInfo("abc", "Example Set", available=2, expected=100)]
    dialog._filter()
    dialog.set_list.setCurrentRow(0)
    dialog.payloads = [card(), card("r", "rare")]
    dialog._art_statuses = {"c": "Download needed", "r": "Download needed"}
    dialog._options_changed()
    dialog._page(1)
    assert not dialog.next.isEnabled()
    dialog.partial.setChecked(True)
    assert dialog.next.isEnabled()
    assert "5 physical cards" in dialog.summary.text()
    dialog.spins["common"].setValue(0)
    assert "1 physical cards" in dialog.summary.text()
    dialog._page(2)
    rare = next(
        dialog.tree.topLevelItem(i)
        for i in range(dialog.tree.topLevelItemCount())
        if dialog.tree.topLevelItem(i).text(0) == "Rare"
    )
    rare.child(0).setData(2, C.Qt.ItemDataRole.EditRole, 7)
    assert dialog.settings.overrides["r"] == 7
    assert "7 physical cards" in dialog.summary.text()
    dialog.card_search.setText("not found")
    assert all(
        dialog.tree.topLevelItem(i).isHidden()
        for i in range(dialog.tree.topLevelItemCount())
    )
    dialog.reject()
    app.processEvents()


def test_large_inventory_has_no_search_page_limit():
    cards = [card(str(i)) for i in range(1200)]
    settings = InventorySettings()
    assert totals(eligible_cards(cards, settings), settings) == (1200, 4800)


def test_ui_worker_remains_responsive_and_cancels_safely(catalog, monkeypatch):
    from threading import Event
    from PyQt6 import QtWidgets as W, QtCore as C
    from mtg_ui.print_set_dialog import PrintSetDialog

    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(PrintSetDialog, "_discover", lambda self: None)
    dialog = PrintSetDialog(service=catalog)
    dialog.show()
    release = Event()
    callbacks, gui_events = [], []

    def work(worker):
        release.wait(5)
        return "ready"

    dialog._start(work, callbacks.append, "Preparing your cards")
    worker = dialog.worker
    dialog.reject()
    assert worker.cancelled.is_set()
    assert dialog.isVisible()
    loop = C.QEventLoop()
    worker.finished.connect(loop.quit)
    timer = C.QTimer(dialog)
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(10000)

    def responsive():
        gui_events.append("responsive")
        release.set()

    C.QTimer.singleShot(0, responsive)
    loop.exec()
    timer.stop()
    app.processEvents()
    assert gui_events == ["responsive"]
    assert dialog.worker is None
    assert not callbacks
    assert "Stopped safely" in dialog.status.text()
    dialog.reject()
