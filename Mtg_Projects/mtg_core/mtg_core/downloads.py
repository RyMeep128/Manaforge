"""Bounded-memory, resumable file downloads shared by data and artwork jobs.

Call from a worker. Progress callbacks run on that worker, never on the GUI thread.
One process must own a destination; the application already enforces single launch.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi

from .network import defer_provider, get_download_logger, wait_for_request


class DownloadCancelled(Exception):
    """Cooperative cancellation; a resumable partial file may remain."""


class IntegrityError(ValueError):
    """The response does not match the expected artifact."""


@dataclass(frozen=True)
class DownloadProgress:
    downloaded: int
    total: int | None
    bytes_per_second: float
    phase: str = "downloading"

    @property
    def remaining_seconds(self):
        if self.total is None or self.bytes_per_second <= 0:
            return None
        return max(0, self.total - self.downloaded) / self.bytes_per_second


def check_space(path, required):
    if required < 0:
        raise ValueError("Required disk space cannot be negative")
    if shutil.disk_usage(Path(path).parent).free < required + 16 * 1024**2:
        raise OSError(
            "Insufficient disk space. Free space or choose another data location."
        )


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    """Caller serializes writers; a crash cannot leave half a JSON document."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an HTTPS download URL without embedded credentials")


class _HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DownloadManager:
    """Bound concurrency and retry transient failures without replacing working data."""

    def __init__(
        self,
        *,
        concurrency=2,
        retries=3,
        timeout=30,
        opener=None,
        provider_intervals=None,
    ):
        if concurrency < 1 or retries < 0 or timeout <= 0:
            raise ValueError("Invalid download limits")
        self._slots = threading.BoundedSemaphore(concurrency)
        self._locks = [threading.Lock() for _ in range(64)]
        self.retries, self.timeout = retries, timeout
        self.provider_intervals = dict(provider_intervals or {})
        if any(value < 0 for value in self.provider_intervals.values()):
            raise ValueError("Provider intervals cannot be negative")
        context = ssl.create_default_context(cafile=certifi.where())
        self._open = (
            opener
            or urllib.request.build_opener(
                _HTTPSRedirect(), urllib.request.HTTPSHandler(context=context)
            ).open
        )

    def download(
        self,
        url,
        destination,
        *,
        sha256=None,
        size=None,
        max_bytes=None,
        cancel=None,
        progress=None,
        validate=None,
    ):
        validate_url(url)
        if sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise ValueError("Provide a valid SHA-256 checksum")
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError("Invalid download size")
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
            raise ValueError("Invalid download limit")
        path = Path(destination).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        cancel = cancel or threading.Event()
        lock = self._locks[hash(str(path)) % len(self._locks)]
        while not lock.acquire(timeout=0.1):
            self._check_cancel(cancel)
        acquired = False
        try:
            while not self._slots.acquire(timeout=0.1):
                self._check_cancel(cancel)
            acquired = True
            return self._download(
                url, path, sha256, size, max_bytes, cancel, progress, validate
            )
        finally:
            if acquired:
                self._slots.release()
            lock.release()

    @staticmethod
    def _check_cancel(cancel):
        if cancel.is_set():
            raise DownloadCancelled("Download cancelled; partial data was preserved.")

    def _download(self, url, path, digest, size, maximum, cancel, progress, validate):
        part = path.with_name(path.name + ".part")
        metadata = path.with_name(path.name + ".part.json")
        identity = {"url": url, "sha256": digest, "size": size}
        for attempt in range(self.retries + 1):
            self._check_cancel(cancel)
            state = {}
            try:
                state = json.loads(metadata.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            if not isinstance(state, dict) or state.get("identity") != identity:
                part.unlink(missing_ok=True)
                state = {}
            offset = part.stat().st_size if part.exists() else 0
            validator = state.get("validator")
            # Never append to an unidentifiable representation.
            if offset and not validator:
                part.unlink()
                offset = 0
            headers = {"User-Agent": "Manaforge/infra", "Accept-Encoding": "identity"}
            if offset:
                headers.update({"Range": f"bytes={offset}-", "If-Range": validator})
            wait_for_request(
                url,
                cancel=cancel,
                interval=self.provider_intervals.get(
                    urllib.parse.urlsplit(url).hostname
                ),
            )
            try:
                with self._open(
                    urllib.request.Request(url, headers=headers), timeout=self.timeout
                ) as response:
                    validate_url(response.geturl())
                    status = response.status
                    length = response.headers.get("Content-Length")
                    length = int(length) if length is not None else None
                    if (
                        response.headers.get("Content-Encoding", "identity")
                        != "identity"
                    ):
                        raise IntegrityError(
                            "Unexpected compressed HTTP representation"
                        )
                    if status == 206:
                        match = re.fullmatch(
                            r"bytes (\d+)-(\d+)/(\d+)",
                            response.headers.get("Content-Range", ""),
                        )
                        if (
                            not match
                            or int(match[1]) != offset
                            or int(match[2]) < offset
                            or int(match[2]) >= int(match[3])
                        ):
                            raise IntegrityError("Invalid resumed download range")
                        total = int(match[3])
                        if length is not None and length != int(match[2]) - offset + 1:
                            raise IntegrityError("Invalid resumed response size")
                        current_validator = response.headers.get(
                            "ETag"
                        ) or response.headers.get("Last-Modified")
                        if (
                            current_validator
                            and validator
                            and current_validator != validator
                        ):
                            raise IntegrityError("Download changed during resume")
                    elif status == 200:
                        offset = (
                            0  # Server ignored Range or the representation changed.
                        )
                        total = length
                    else:
                        raise IntegrityError(f"Unexpected HTTP status {status}")
                    if size is not None and total is not None and total != size:
                        raise IntegrityError("Download size differs from manifest")
                    if maximum is not None and total is not None and total > maximum:
                        raise IntegrityError("Download exceeds supported size")
                    check_space(path, max(0, (size or total or 0) - offset))
                    etag = response.headers.get("ETag")
                    validator = (
                        etag
                        if etag and not etag.startswith("W/")
                        else response.headers.get("Last-Modified")
                    )
                    atomic_json(
                        metadata, {"identity": identity, "validator": validator}
                    )
                    started, initial = time.monotonic(), offset
                    with part.open("ab" if offset else "wb") as stream:
                        while True:
                            self._check_cancel(cancel)
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            if (
                                maximum is not None and offset + len(chunk) > maximum
                            ) or (size is not None and offset + len(chunk) > size):
                                raise IntegrityError("Download exceeds supported size")
                            check_space(path, len(chunk))
                            stream.write(chunk)
                            offset += len(chunk)
                            if progress:
                                progress(
                                    DownloadProgress(
                                        offset,
                                        size if size is not None else total,
                                        (offset - initial)
                                        / max(0.001, time.monotonic() - started),
                                    )
                                )
                        stream.flush()
                        os.fsync(stream.fileno())
                    if (size is not None and offset != size) or (
                        total is not None and offset != total
                    ):
                        raise urllib.error.URLError(
                            "Download interrupted before expected length"
                        )
                self._check_cancel(cancel)
                if progress:
                    progress(DownloadProgress(offset, offset, 0, "verifying"))
                if digest is not None and file_sha256(part) != digest.lower():
                    raise IntegrityError("Download SHA-256 checksum mismatch")
                if validate:
                    validate(part)
                self._check_cancel(cancel)
                os.replace(part, path)
                metadata.unlink(missing_ok=True)
                if progress:
                    progress(DownloadProgress(offset, offset, 0, "completed"))
                return path
            except IntegrityError:
                part.unlink(missing_ok=True)
                metadata.unlink(missing_ok=True)
                raise
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                ConnectionError,
                http.client.IncompleteRead,
            ) as exc:
                code = getattr(exc, "code", None)
                delay = min(30, 2**attempt)
                if code == 416:
                    part.unlink(missing_ok=True)
                    metadata.unlink(missing_ok=True)
                elif code is not None and code not in (408, 429, 500, 502, 503, 504):
                    exc.close()
                    raise
                if code in (429, 503):
                    value = exc.headers.get("Retry-After", "60")
                    try:
                        delay = max(1, float(value))
                    except ValueError:
                        try:
                            delay = max(
                                1,
                                parsedate_to_datetime(value).timestamp() - time.time(),
                            )
                        except (ValueError, TypeError, OverflowError):
                            delay = 60
                    defer_provider(url, delay)
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                get_download_logger().warning(
                    "download retry=%s status=%s provider=%s",
                    attempt + 1,
                    code,
                    urllib.parse.urlsplit(url).hostname,
                )
                if attempt == self.retries:
                    raise
                if cancel.wait(delay):
                    self._check_cancel(cancel)


_default_manager = None
_default_lock = threading.Lock()


def get_download_manager():
    global _default_manager
    with _default_lock:
        if _default_manager is None:
            _default_manager = DownloadManager()
        return _default_manager
