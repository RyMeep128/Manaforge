from contextlib import closing
import gzip
import io
import json
from pathlib import Path
import threading
import uuid

from PIL import Image
import pytest

from mtg_core.artwork_downloads import fill_artwork, clear_optional_artwork
from mtg_core.bulk_install import import_cards, import_rulings, records
from mtg_core.datasets import InstallationState
from mtg_core.downloads import DownloadCancelled
from mtg_core.installation import InstallationEngine, InstallPlan, MONTH
from mtg_core.services import CardService


def card(identity=1, *, version=1):
    return dict(
        object="card",
        id=str(uuid.UUID(int=identity)),
        oracle_id=str(uuid.UUID(int=identity + 100)),
        name="Fixture " + str(identity),
        set="tst",
        collector_number=str(identity),
        released_at="2020-01-01",
        oracle_text="Draw a card." if version == 1 else "Draw two cards.",
        image_uris={"png": f"https://cards.scryfall.io/{identity}.png?v={version}"},
    )


def service(tmp_path):
    return CardService(
        db_path=str(tmp_path / "cards.sqlite3"),
        image_root=str(tmp_path / "artwork"),
        fetch_bytes_fn=lambda url: b"injected fixture",
    )


def export(path, items):
    path.write_bytes(
        gzip.compress(b"\n".join(json.dumps(item).encode() for item in items))
    )
    return path


def test_card_update_preserves_favorites_custom_assets_and_refreshes_indexes(tmp_path):
    svc = service(tmp_path)
    old = card()
    svc.database.upsert_card_payload(old)
    svc.set_artwork_favorite(old["oracle_id"], old["id"])
    asset = svc.store_image_bytes(b"custom art", source="custom")
    svc.set_print_image_asset(old["id"], asset, source="custom")
    path = export(tmp_path / "cards.gz", [card(version=2), card(2)])
    assert (
        import_cards(
            path, svc.database, "v2", cancel=threading.Event(), report=lambda p: None
        )
        == 2
    )
    assert svc.get_artwork_favorite(old["oracle_id"]) == old["id"]
    assert svc.database.get_image_record(old["id"]).asset_id == asset
    assert svc.get_card(card_id=old["id"])["oracle_text"] == "Draw two cards."
    assert svc.database.get_sync_state("installed-default_cards")["version"] == "v2"
    assert svc.database.search_syntax('o:"Draw two cards"')


def test_invalid_or_cancelled_card_import_keeps_working_data_and_version(tmp_path):
    svc = service(tmp_path)
    svc.database.upsert_card_payload(card())
    bad = export(tmp_path / "bad.gz", [card(version=2), dict(object="not-a-card")])
    with pytest.raises(ValueError):
        import_cards(
            bad, svc.database, "bad", cancel=threading.Event(), report=lambda p: None
        )
    assert svc.get_card(card_id=card()["id"])["oracle_text"] == "Draw a card."
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(DownloadCancelled):
        import_cards(bad, svc.database, "bad", cancel=cancelled, report=lambda p: None)
    assert svc.database.get_sync_state("installed-default_cards") is None


def test_jsonl_gzip_and_legacy_array_are_streamed(tmp_path):
    path = export(tmp_path / "lines.gz", [card(), card(2)])
    assert len(list(records(path))) == 2
    path = tmp_path / "array.json"
    path.write_text(json.dumps([card()]))
    assert list(records(path)) == [card()]


def test_bulk_rulings_empty_snapshots_and_failed_import_preserve_cache(tmp_path):
    svc = service(tmp_path)
    for value in (card(), card(2)):
        svc.database.upsert_card_payload(value)
    ruling = dict(
        object="ruling",
        oracle_id=card()["oracle_id"],
        source="wotc",
        published_at="2026-01-01",
        comment="Fixture ruling.",
    )
    path = export(tmp_path / "rulings.gz", [ruling])
    import_rulings(path, svc, "r1", cancel=threading.Event(), report=lambda p: None)
    assert len(svc.get_rulings(card()["oracle_id"])["rulings"]) == 1
    assert svc.get_rulings(card(2)["oracle_id"])["rulings"] == []
    export(path, [dict(ruling, comment=None)])
    with pytest.raises(ValueError):
        import_rulings(path, svc, "r2", cancel=threading.Event(), report=lambda p: None)
    assert (
        svc.get_rulings(card()["oracle_id"])["rulings"][0]["comment"]
        == "Fixture ruling."
    )


def png():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(stream, format="PNG")
    return stream.getvalue()


class Images:
    def __init__(self):
        self.calls = []

    def download(self, url, destination, **kwargs):
        self.calls.append(url)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(png())
        if kwargs.get("validate"):
            kwargs["validate"](Path(destination))
        return Path(destination)


def test_offline_artwork_reuses_images_updates_changed_urls_and_aliases_back(tmp_path):
    svc = service(tmp_path)
    payload = card()
    payload["card_faces"] = [
        dict(name="Front", image_uris=payload["image_uris"]),
        dict(name="Back", image_uris={"png": "https://cards.scryfall.io/back.png?v=1"}),
    ]
    payload.pop("image_uris")
    svc.database.upsert_card_payload(payload)
    state = InstallationState(tmp_path / "state.sqlite3")
    images = Images()
    fill_artwork(
        svc, state, cancel=threading.Event(), report=lambda p: None, downloader=images
    )
    assert len(images.calls) == 2
    front = svc.get_image_path(payload["id"])
    assert svc.get_image_path(payload["id"], "back") == svc.get_image_path(
        payload["id"], "face-1"
    )
    assert Path(front).parent.name != "mtg_core_cache"
    fill_artwork(
        svc, state, cancel=threading.Event(), report=lambda p: None, downloader=images
    )
    assert len(images.calls) == 2
    payload["card_faces"][0]["image_uris"]["png"] = (
        "https://cards.scryfall.io/1.png?v=2"
    )
    svc.database.upsert_card_payload(payload)
    fill_artwork(
        svc, state, cancel=threading.Event(), report=lambda p: None, downloader=images
    )
    assert len(images.calls) == 3


def test_artwork_pause_checkpoints_resume_and_cleanup_preserves_canonical_assets(
    tmp_path,
):
    svc = service(tmp_path)
    for value in (card(), card(2)):
        svc.database.upsert_card_payload(value)
    state = InstallationState(tmp_path / "state.sqlite3")
    images = Images()
    cancel = threading.Event()
    with pytest.raises(DownloadCancelled):
        fill_artwork(
            svc, state, cancel=cancel, report=lambda p: cancel.set(), downloader=images
        )
    assert state.get("artwork_checkpoint")["last_card"] == card()["id"]
    fill_artwork(
        svc, state, cancel=threading.Event(), report=lambda p: None, downloader=images
    )
    assert len(images.calls) == 2
    with closing(svc.database.connect()) as db:
        asset = db.execute("SELECT asset_id FROM image_manifest LIMIT 1").fetchone()[0]
    canonical = svc.get_image_path(card()["id"])
    assert (
        clear_optional_artwork(svc, cancel=threading.Event(), report=lambda p: None)
        == 0
    )
    assert Path(canonical).exists() and svc.get_image_bytes(asset)


def test_monthly_checks_and_existing_catalog_location_survive_upgrades(
    tmp_path, monkeypatch
):
    from mtg_core import installation

    root = tmp_path / "existing"
    root.mkdir()
    old = CardService(db_path=str(root / "card_data.sqlite3"))
    old.database.upsert_card_payload(card())
    monkeypatch.setattr(installation, "core_data_root", lambda: root)
    state = InstallationState(tmp_path / "state.sqlite3")
    engine = InstallationEngine(state)
    engine.configure(tmp_path / "new", "on_demand")
    assert state.get("catalog_path") == str(old.database.db_path)
    state.set("setup_complete", True)
    state.set("last_complete_update_check", 100)
    assert not engine.needs_update(100 + MONTH - 1)
    assert engine.needs_update(100 + MONTH)
    state.set("last_update_attempt", 100 + MONTH - 1)
    assert not engine.needs_update(100 + MONTH)
    with pytest.raises(ValueError, match="location"):
        engine.configure("", "on_demand")


def test_failed_update_never_marks_setup_complete(tmp_path, monkeypatch):
    svc = service(tmp_path)
    state = InstallationState(tmp_path / "state.sqlite3")
    engine = InstallationEngine(state, service=svc)
    engine.configure(tmp_path / "data", "on_demand")
    plan = InstallPlan(
        {
            "default_cards": {
                "updated_at": "v1",
                "download_uri": "https://data.scryfall.io/cards.gz",
            }
        },
        {"manifest_version": 1, "datasets": []},
        0,
        0,
        0,
    )

    class Broken:
        def download(self, *args, **kwargs):
            raise OSError("Offline")

    engine.downloader = Broken()
    with pytest.raises(OSError, match="Offline"):
        engine.run(
            cancel=threading.Event(), report=lambda p: None, plan=plan, setup=True
        )
    assert not state.get("setup_complete", False)


def test_setup_downloads_and_installs_same_base_datasets_without_artwork(
    tmp_path, monkeypatch
):
    from mtg_core import installation
    from mtg_core.recommendation_packaging import build_distribution
    from mtg_core.recommendations import RecommendationStore
    import shutil

    monkeypatch.setattr(installation, "core_data_root", lambda: tmp_path / "legacy")
    source = tmp_path / "source"
    source.mkdir()
    collected = RecommendationStore(source / "archidekt.sqlite3")
    collected.ingest_members(
        "private-fixture",
        "v1",
        "private-url",
        {card()["oracle_id"]: 1, card(2)["oracle_id"]: 0},
    )
    packaged = tmp_path / "packages"
    manifest = build_distribution(
        source, packaged, "2026.10.26-alpha.1", sources=["archidekt"]
    )
    cards = export(tmp_path / "cards.gz", [card(), card(2)])
    ruling = dict(
        object="ruling",
        oracle_id=card()["oracle_id"],
        source="wotc",
        published_at="2026-01-01",
        comment="Ruling",
    )
    rulings = export(tmp_path / "rulings.gz", [ruling])

    class Downloads:
        def __init__(self):
            self.calls = []

        def download(self, url, destination, **kwargs):
            self.calls.append(url)
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if url.endswith("manifest.json"):
                destination.write_text(json.dumps(manifest))
            else:
                selected = (
                    cards
                    if url.endswith("cards.gz")
                    else rulings
                    if url.endswith("rulings.gz")
                    else packaged / Path(url).name
                )
                shutil.copyfile(selected, destination)
            if kwargs.get("validate"):
                kwargs["validate"](destination)
            return destination

    downloads = Downloads()

    def metadata(url):
        kind = url.rsplit("/", 1)[-1]
        return dict(
            type=kind,
            updated_at="2026-10-26",
            jsonl_download_uri="https://data.scryfall.io/"
            + ("cards.gz" if kind == "default_cards" else "rulings.gz"),
        )

    state = InstallationState(tmp_path / "state.sqlite3")
    engine = InstallationEngine(state, fetch_metadata=metadata, downloader=downloads)
    engine.configure(tmp_path / "data", "on_demand")
    plan = engine.plan(cancel=threading.Event(), report=lambda p: None)
    engine.run(cancel=threading.Event(), report=lambda p: None, plan=plan, setup=True)
    assert state.get("setup_complete") is True
    assert len(engine.service.database.search_syntax("o:draw")) == 2
    assert engine.service.get_rulings(card()["oracle_id"])["rulings"]
    assert state.installed("recommendations-archidekt")
    assert not any(".png" in url for url in downloads.calls)
    assert not state.get("update_pending")
