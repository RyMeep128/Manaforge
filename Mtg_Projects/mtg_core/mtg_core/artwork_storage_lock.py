"""Cooperative, cross-process locking for immutable artwork publication."""

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import threading
import time

from .downloads import DownloadCancelled


def cancelled(event):
    if event is not None and event.is_set():
        raise DownloadCancelled("Artwork storage operation paused; progress is saved.")


_guard = threading.Lock()
_locks = {}
_held = threading.local()


def artwork_root(path):
    path = Path(path).absolute()
    for parent in path.parents:
        if parent.name == "assets":
            return parent.parent
    return path.parent


@contextmanager
def storage_lock(root, cancel=None):
    """All managed artwork writers use this lock; readers remain unblocked."""
    root = Path(root).resolve()
    key = os.path.normcase(str(root))
    with _guard:
        mutex = _locks.setdefault(key, threading.RLock())
    while not mutex.acquire(timeout=0.1):
        cancelled(cancel)
    held = getattr(_held, "roots", {})
    try:
        if key in held:
            yield
            return
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".artwork-storage.lock").open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            while True:
                cancelled(cancel)
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.1)
            held[key] = True
            _held.roots = held
            try:
                yield
            finally:
                del held[key]
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        mutex.release()
