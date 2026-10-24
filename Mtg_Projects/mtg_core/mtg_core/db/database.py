"""Public database facade; internal operation groups share its connection and path."""
from __future__ import annotations

import os
import sqlite3
from mtg_core.paths import core_data_root
from .catalog import CatalogRepository
from .schema import SchemaOperations
from .cards import CardOperations
from .search import SearchOperations
from .images import ImageOperations
from .preferences import PreferenceOperations
from .sync_state import SyncStateOperations


def default_db_path() -> str:
    return str(core_data_root() / "card_data.sqlite3")


class CardDatabase(
    SchemaOperations, CardOperations, SearchOperations,
    ImageOperations, PreferenceOperations, SyncStateOperations,
):
    """One database API composed from internal, stateless operation groups.

    Groups share this instance's path and connection factory; calls between
    groups go through self so overrides and transaction hooks remain effective.
    Callers should instantiate this facade, not the individual groups.
    """
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_db_path()
        if self.db_path != ":memory:":
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._ensure_schema()
        self._catalog = CatalogRepository(self)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection
