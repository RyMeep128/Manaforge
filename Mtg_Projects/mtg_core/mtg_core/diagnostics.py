"""Shared, bounded diagnostics; logging must not prevent an operation's recovery."""
import logging
from logging.handlers import RotatingFileHandler
import os
from threading import Lock

from mtg_core.paths import core_data_root

_lock = Lock()
_handler = None


def get_logger(name):
    global _handler
    parent = logging.getLogger('manaforge')
    with _lock:
        if _handler is None:
            failure = None
            try:
                root = core_data_root() / 'logs'
                root.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(root / f'diagnostics-{os.getpid()}.log',
                    maxBytes=5_000_000, backupCount=3, encoding='utf-8')
            except OSError as exc:
                handler = logging.StreamHandler()
                failure = exc
            handler.setLevel(logging.WARNING)
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
            parent.addHandler(handler)
            parent.setLevel(logging.WARNING)
            _handler = handler
            if failure is not None:
                parent.warning('Could not open diagnostic file; using stderr: %s', failure)
    return logging.getLogger(f'manaforge.{name}')
