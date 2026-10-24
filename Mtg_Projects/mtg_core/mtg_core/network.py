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
    global _next_request, _cooldown_until
    host = (urllib.parse.urlsplit(request.full_url).hostname or "").lower()
    paced = host == "scryfall.com" or host.endswith(".scryfall.com") or host.endswith(".scryfall.io")
    logger = get_download_logger()
    for attempt in range(MAX_RETRIES + 1):
        if paced:
            with _lock:
                delay = max(_next_request, _cooldown_until) - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                _next_request = time.monotonic() + REQUEST_INTERVAL
        started = time.monotonic()
        try:
            with opener(request, timeout=30, context=context) as response:
                payload = response.read()
                logger.info("request status=%s bytes=%s elapsed=%.3f url=%s",
                            getattr(response, "status", 200), len(payload),
                            time.monotonic() - started, request.full_url)
                return payload
        except urllib.error.HTTPError as error:
            logger.warning("request status=%s attempt=%s url=%s", error.code, attempt + 1, request.full_url)
            if error.code != 429 or not paced:
                raise
            seconds = _retry_seconds(error.headers)
            error.close()
            with _lock:
                _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)
            logger.warning("rate_limit cooldown_seconds=%.1f retry=%s/%s url=%s",
                           seconds, attempt + 1, MAX_RETRIES, request.full_url)
            if attempt == MAX_RETRIES:
                raise RateLimitExceeded(
                    f"Scryfall rate limit persisted after {MAX_RETRIES} retries; "
                    f"download stopped at its checkpoint. Wait at least {seconds:.0f} seconds before Resume."
                ) from error
        except Exception:
            logger.exception("request failed url=%s", request.full_url)
            raise
