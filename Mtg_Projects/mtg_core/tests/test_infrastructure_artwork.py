from concurrent.futures import ThreadPoolExecutor
import threading

from mtg_core.services import CardService


def make_service(tmp_path, fetch):
    service = CardService(
        db_path=str(tmp_path / "cards.sqlite3"),
        image_root=str(tmp_path / "images"),
        fetch_bytes_fn=fetch,
    )
    service.database.upsert_card_payload(
        {
            "id": "printing",
            "oracle_id": "oracle",
            "name": "Fixture",
            "set": "tst",
            "collector_number": "1",
            "image_uris": {"png": "https://cards.scryfall.io/fixture.png"},
        }
    )
    return service


def test_concurrent_artwork_requests_fetch_once_and_remain_available_offline(tmp_path):
    calls = []
    started, release = threading.Event(), threading.Event()

    def fetch(url):
        calls.append(url)
        started.set()
        assert release.wait(5)
        return b"fixture artwork"

    service = make_service(tmp_path, fetch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.ensure_image, "printing")
        assert started.wait(5)
        second = executor.submit(service.ensure_image, "printing")
        release.set()
        assert first.result() == second.result()
    assert len(calls) == 1
    assert service.ensure_image("printing", allow_remote=False)


def test_missing_asset_is_not_materialized_as_empty_artwork(tmp_path):
    service = make_service(tmp_path, lambda url: b"fixture artwork")
    path = service.ensure_image("printing")
    record = service.database.get_image_record("printing")
    asset = service.database.get_image_asset(record.asset_id)
    from pathlib import Path

    Path(path).unlink()
    service.database._resolve_image_asset_storage_path(asset.storage_path).unlink(
        missing_ok=True
    )
    assert service.get_image_path("printing") is None
    assert service.ensure_image("printing", allow_remote=False) is None
    restored = service.ensure_image("printing")
    assert Path(restored).read_bytes() == b"fixture artwork"
