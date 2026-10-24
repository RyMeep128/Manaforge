import io
import logging
import urllib.error
import urllib.request
from email.utils import formatdate

import pytest
from mtg_core import network
from mtg_core.services import CardService


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(network.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(network.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    monkeypatch.setattr(network, "_next_request", 0.0)
    monkeypatch.setattr(network, "_cooldown_until", 0.0)
    monkeypatch.setattr(network, "_logger", logging.getLogger("network-test"))
    return now


def test_shared_spacing_for_api_and_images(clock):
    starts = []
    def opener(*args, **kwargs):
        starts.append(clock[0])
        return io.BytesIO(b"ok")
    for host in ["api.scryfall.com", "cards.scryfall.io", "api.scryfall.com"]:
        network.read_response(urllib.request.Request("https://" + host + "/test"), opener=opener, context=None)
    assert starts == [100, 100.25, 100.5]


@pytest.mark.parametrize("header,delay", [("90", 90), ("1", 60), ("invalid", 60)])
def test_cooldown_retries_same_request(clock, header, delay):
    starts = []
    def opener(request, **kwargs):
        starts.append((clock[0], request.full_url))
        if len(starts) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "limited", {"Retry-After": header}, io.BytesIO())
        return io.BytesIO(b"ok")
    result = network.read_response(urllib.request.Request("https://api.scryfall.com/test"), opener=opener, context=None)
    assert result == b"ok"
    assert starts[1][0] - starts[0][0] == delay
    assert starts[0][1] == starts[1][1]


def test_http_date_retry_after(monkeypatch):
    monkeypatch.setattr(network.time, "time", lambda: 1000)
    assert network._retry_seconds({"Retry-After": formatdate(1120, usegmt=True)}) == 120


def test_repeated_limits_stop_and_preserve_cooldown(clock):
    starts = []
    def opener(request, **kwargs):
        starts.append(clock[0])
        raise urllib.error.HTTPError(request.full_url, 429, "limited", {}, io.BytesIO())
    with pytest.raises(network.RateLimitExceeded):
        network.read_response(urllib.request.Request("https://cards.scryfall.io/test"), opener=opener, context=None)
    assert starts == [100, 160, 220, 280]
    assert network._cooldown_until == 340


def test_non_rate_error_is_not_retried(clock):
    def opener(request, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, io.BytesIO())
    with pytest.raises(urllib.error.HTTPError):
        network.read_response(urllib.request.Request("https://api.scryfall.com/test"), opener=opener, context=None)
    assert clock[0] == 100


def test_image_rate_limit_keeps_checkpoint(tmp_path, clock):
    card = {"id": "test-card", "oracle_id": "test-oracle", "name": "Test", "set": "tst", "collector_number": "1", "image_uris": {"png": "https://cards.scryfall.io/test.png"}}
    def limited(url):
        raise network.RateLimitExceeded("cooldown exhausted")
    service = CardService(db_path=str(tmp_path / "cards.sqlite3"), fetch_json_fn=lambda url: {"data": [card], "has_more": False}, fetch_bytes_fn=limited)
    result = service.process_bulk_download_chunk(query="l:eng game:paper")
    assert result.status == "failed"
    assert result.page_offset == 0
    assert result.total_scanned == 0
    assert result.total_failed == 0
    service.fetch_bytes_fn = lambda url: b"x" * 5000
    result = service.process_bulk_download_chunk(query="l:eng game:paper")
    assert result.completed
    assert result.total_downloaded == 1


def test_rotating_log_records_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(network, "_logger", None)
    monkeypatch.setattr(network, "core_data_root", lambda: tmp_path)
    original_get_logger = logging.getLogger
    isolated = logging.Logger("isolated-download-log")
    monkeypatch.setattr(network.logging, "getLogger", lambda name=None: isolated if name == "mtg_core.downloads" else original_get_logger(name))
    logger = network.get_download_logger()
    logger.info("card_failed name=Example card_id=example")
    for handler in logger.handlers:
        handler.flush()
        assert handler.maxBytes == 5_000_000
        assert handler.backupCount == 3
        handler.close()
    logs = list((tmp_path / "logs").glob("downloads-*.log"))
    assert len(logs) == 1
    assert "card_failed name=Example card_id=example" in logs[0].read_text()


def test_missing_image_at_end_of_page_advances_once(tmp_path, clock):
    missing = {"id": "missing", "oracle_id": "oracle-missing", "name": "Missing art", "set": "art", "collector_number": "1"}
    good = {"id": "good", "oracle_id": "oracle-good", "name": "Good", "set": "tst", "collector_number": "2", "image_uris": {"png": "https://cards.scryfall.io/good.png"}}
    calls = []
    def fetch(url):
        calls.append(url)
        if url == "https://api.scryfall.com/page2":
            return {"data": [good], "has_more": False}
        return {"data": [missing], "has_more": True, "next_page": "https://api.scryfall.com/page2"}
    service = CardService(db_path=str(tmp_path / "cards.sqlite3"), fetch_json_fn=fetch, fetch_bytes_fn=lambda url: b"x" * 5000)
    first = service.process_bulk_download_chunk(query="l:eng game:paper")
    assert first.total_failed == 1
    assert first.total_scanned == 1
    assert first.current_page_url == "https://api.scryfall.com/page2"
    second = service.process_bulk_download_chunk(query="l:eng game:paper")
    assert second.completed
    assert second.total_failed == 1
    assert second.total_scanned == 2
    assert second.total_downloaded == 1
    assert len(calls) == 2


def test_missing_image_advances_before_pause(tmp_path, clock):
    card = {"id": "missing", "oracle_id": "oracle-missing", "name": "Missing art"}
    service = CardService(db_path=str(tmp_path / "cards.sqlite3"), fetch_json_fn=lambda url: {"data": [card], "has_more": False})
    first = service.process_bulk_download_chunk(query="test", should_pause=lambda: True)
    assert first.status == "paused"
    assert first.page_offset == 1
    second = service.process_bulk_download_chunk(query="test")
    assert second.completed
    assert second.total_failed == 1
