"""Failure-oriented regressions for CI; all HTTP responses are local fixtures."""

import hashlib
import io
import json
import threading
import urllib.error

import pytest

from mtg_core import downloads
from mtg_core.downloads import DownloadCancelled, DownloadManager, IntegrityError


URL = "https://fixtures.example/data"


class Response(io.BytesIO):
    def __init__(self, data, *, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(data)), "ETag": '"v1"'}

    def geturl(self):
        return URL


@pytest.fixture(autouse=True)
def no_network_pacing(monkeypatch):
    monkeypatch.setattr(downloads, "wait_for_request", lambda *a, **k: None)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def test_verified_download_streams_and_keeps_working_file_until_complete(tmp_path):
    path = tmp_path / "dataset"
    path.write_bytes(b"old")
    raw = b"x" * (2 * 1024**2 + 23)
    events = []

    def report(event):
        events.append(event)
        if event.phase != "completed":
            assert path.read_bytes() == b"old"

    manager = DownloadManager(opener=lambda *a, **k: Response(raw))
    manager.download(URL, path, sha256=digest(raw), size=len(raw), progress=report)
    assert path.read_bytes() == raw
    assert len([e for e in events if e.phase == "downloading"]) == 3
    assert events[-1].phase == "completed"
    assert not path.with_name("dataset.part").exists()


@pytest.mark.parametrize(
    "options", [dict(sha256="0" * 64), dict(size=3), dict(max_bytes=3)]
)
def test_invalid_download_never_replaces_existing_file(tmp_path, options):
    path = tmp_path / "dataset"
    path.write_bytes(b"old")
    manager = DownloadManager(opener=lambda *a, **k: Response(b"new payload"))
    with pytest.raises(IntegrityError):
        manager.download(URL, path, **options)
    assert path.read_bytes() == b"old"


def test_cancelled_download_resumes_in_a_new_manager(tmp_path):
    path = tmp_path / "dataset"
    raw = b"a" * 1024**2 + b"b" * 19
    cancel = threading.Event()
    manager = DownloadManager(opener=lambda *a, **k: Response(raw))
    with pytest.raises(DownloadCancelled):
        manager.download(
            URL,
            path,
            sha256=digest(raw),
            size=len(raw),
            cancel=cancel,
            progress=lambda event: cancel.set(),
        )
    assert path.with_name("dataset.part").stat().st_size == 1024**2

    def resume(request, **kwargs):
        assert request.get_header("Range") == f"bytes={1024**2}-"
        assert request.get_header("If-range") == '"v1"'
        return Response(
            raw[1024**2 :],
            status=206,
            headers={
                "Content-Range": f"bytes {1024**2}-{len(raw) - 1}/{len(raw)}",
                "Content-Length": "19",
                "ETag": '"v1"',
            },
        )

    DownloadManager(opener=resume).download(
        URL, path, sha256=digest(raw), size=len(raw)
    )
    assert path.read_bytes() == raw


def test_ignored_range_restarts_instead_of_appending(tmp_path):
    path = tmp_path / "dataset"
    path.with_name("dataset.part").write_bytes(b"stale")
    path.with_name("dataset.part.json").write_text(
        json.dumps(
            {
                "identity": {"url": URL, "sha256": None, "size": None},
                "validator": '"v1"',
            }
        )
    )
    DownloadManager(opener=lambda *a, **k: Response(b"fresh")).download(URL, path)
    assert path.read_bytes() == b"fresh"


def test_semantic_validation_failure_preserves_old_file(tmp_path):
    path = tmp_path / "dataset"
    path.write_bytes(b"working")

    def reject(candidate):
        raise ValueError("Invalid schema")

    with pytest.raises(ValueError, match="schema"):
        DownloadManager(opener=lambda *a, **k: Response(b"bad")).download(
            URL, path, validate=reject
        )
    assert path.read_bytes() == b"working"


def test_disk_failure_and_https_redirect_preserve_data(tmp_path, monkeypatch):
    path = tmp_path / "dataset"
    path.write_bytes(b"working")

    def full(*args):
        raise OSError("Insufficient disk space")

    monkeypatch.setattr(downloads, "check_space", full)
    with pytest.raises(OSError, match="disk"):
        DownloadManager(opener=lambda *a, **k: Response(b"data")).download(URL, path)
    assert path.read_bytes() == b"working"
    with pytest.raises(ValueError, match="HTTPS"):
        downloads._HTTPSRedirect().redirect_request(
            None, None, 302, "", {}, "http://fixtures.example/data"
        )


def test_permanent_http_error_is_not_retried(tmp_path):
    calls = []

    def missing(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError(URL, 404, "missing", {}, io.BytesIO())

    with pytest.raises(urllib.error.HTTPError):
        DownloadManager(opener=missing).download(URL, tmp_path / "data")
    assert len(calls) == 1


def test_official_bulk_export_uses_shared_streaming_interface(tmp_path):
    from mtg_core.sync import stage_bulk_download

    metadata = {
        "type": "rulings",
        "download_uri": "https://data.scryfall.io/rulings.json",
    }
    manager = DownloadManager(opener=lambda *a, **k: Response(b"[]"))
    path, result = stage_bulk_download(
        "rulings",
        tmp_path / "rulings.json",
        fetch_metadata=lambda url: metadata,
        downloader=manager,
    )
    assert path.read_bytes() == b"[]" and result == metadata
    with pytest.raises(ValueError, match="official"):
        stage_bulk_download(
            "rulings",
            path,
            fetch_metadata=lambda url: {
                "type": "rulings",
                "download_uri": "https://untrusted.example/rulings.json",
            },
        )
