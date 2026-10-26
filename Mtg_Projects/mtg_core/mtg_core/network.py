"""Shared Scryfall request pacing, cooldowns, and bounded diagnostic logs."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
import urllib.error
import urllib.parse
from email.utils import parsedate_to_datetime

from mtg_core.paths import core_data_root


class RateLimitExceeded(OSError):
    """Stop a bulk run without advancing past a rate-limited card."""


_lock = threading.Lock()
_next_request = 0.0
_cooldown_until = 0.0
_logger = None
REQUEST_INTERVAL = 0.25  # At most four request starts per second per process.
MAX_RETRIES = 3
_provider_next = {}


def wait_for_request(url, *, cancel=None, interval=None):
    """Reserve a provider request slot, sharing Scryfall pacing with old callers."""
    global _next_request
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    scryfall = host == "scryfall.com" or host.endswith((".scryfall.com", ".scryfall.io"))
    key = "scryfall" if scryfall else host
    spacing = max(REQUEST_INTERVAL, interval or 0) if scryfall else (0.25 if interval is None else interval)
    while True:
        if cancel is not None and cancel.is_set():
            from mtg_core.downloads import DownloadCancelled
            raise DownloadCancelled("Download cancelled; partial data was preserved.")
        with _lock:
            now = time.monotonic()
            due = max(_next_request, _cooldown_until) if scryfall else _provider_next.get(key, 0)
            delay = due - now
            if delay <= 0:
                if scryfall:
                    _next_request = now + spacing
                else:
                    _provider_next[key] = now + spacing
                return
        if cancel is None:
            time.sleep(min(delay, 0.1))
        else:
            cancel.wait(min(delay, 0.1))


def defer_provider(url, seconds):
    """Apply Retry-After to every download using this provider."""
    global _cooldown_until
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    with _lock:
        until = time.monotonic() + max(0, seconds)
        if host == "scryfall.com" or host.endswith((".scryfall.com", ".scryfall.io")):
            _cooldown_until = max(_cooldown_until, until)
        else:
            _provider_next[host] = max(_provider_next.get(host, 0), until)


def get_download_logger():
    global _logger
    if _logger is None:
        logger = logging.getLogger("mtg_core.downloads")
        logger.setLevel(logging.INFO)
        root = core_data_root() / "logs"
        root.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            root / f"downloads-{os.getpid()}.log", maxBytes=5_000_000,
            backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        _logger = logger
    return _logger


def _retry_seconds(headers):
    value = headers.get("Retry-After", "") if headers else ""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            seconds = 60
    return max(60.0, seconds)


def read_response(request, *, opener, context):
    global _cooldown_until
    host = (urllib.parse.urlsplit(request.full_url).hostname or "").lower()
    paced = host == "scryfall.com" or host.endswith(".scryfall.com") or host.endswith(".scryfall.io")
    logger = get_download_logger()
    for attempt in range(MAX_RETRIES + 1):
        if paced:
            wait_for_request(request.full_url)
        started = time.monotonic()
        try:
            with opener(request, timeout=30, context=context) as response:
                payload = response.read()
                logger.info("request status=%s bytes=%s elapsed=%.3f url=%s",
                            getattr(response, "status", 200), len(payload),
                            time.monotonic() - started, host)
                return payload
        except urllib.error.HTTPError as error:
            logger.warning("request status=%s attempt=%s provider=%s", error.code, attempt + 1, host)
            if error.code != 429 or not paced:
                raise
            seconds = _retry_seconds(error.headers)
            error.close()
            with _lock:
                _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)
            logger.warning("rate_limit cooldown_seconds=%.1f retry=%s/%s url=%s",
                           seconds, attempt + 1, MAX_RETRIES, host)
            if attempt == MAX_RETRIES:
                raise RateLimitExceeded(
                    f"Scryfall rate limit persisted after {MAX_RETRIES} retries; "
                    f"download stopped at its checkpoint. Wait at least {seconds:.0f} seconds before Resume."
                ) from error
        except Exception:
            logger.error("request failed provider=%s", host)
            raise
