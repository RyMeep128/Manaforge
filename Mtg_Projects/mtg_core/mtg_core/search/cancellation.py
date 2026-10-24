"""Cooperative cancellation for local database reads, independent of Qt."""
from contextlib import contextmanager
import sqlite3


class SearchCancelled(Exception):
    """The caller no longer needs these results."""


def check_cancelled(should_cancel):
    if should_cancel and should_cancel():
        raise SearchCancelled()


@contextmanager
def search_connection(database, should_cancel=None):
    check_cancelled(should_cancel)
    # These reads need no schema/journal changes. Bound lock waits as well as
    # interrupting expensive SQL through SQLite's progress callback.
    connection = (sqlite3.connect(database.db_path, timeout=0.1)
                  if should_cancel else database.connect())
    connection.row_factory = sqlite3.Row
    try:
        if should_cancel:
            connection.set_progress_handler(lambda: int(should_cancel()), 1000)
        yield connection
        check_cancelled(should_cancel)
    except sqlite3.OperationalError:
        check_cancelled(should_cancel)
        raise
    finally:
        connection.set_progress_handler(None, 0)
        connection.close()
