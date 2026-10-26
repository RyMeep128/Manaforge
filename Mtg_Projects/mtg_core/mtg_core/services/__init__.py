"""Stable application-facing card API composed from internal operation groups."""
from __future__ import annotations

from typing import Callable
from pathlib import Path

from mtg_core.db import CardDatabase
from mtg_core.paths import core_data_root
from mtg_core.rulings import RulingsOperations
from mtg_core.rules_reference import RulesOperations
from mtg_core.sync import RemoteLookupUnavailable, fetch_bytes, fetch_json
from .artwork import ArtworkOperations
from .catalog_sync import CatalogSyncOperations
from .images import ImageOperations
from .search import SearchOperations
from .preferences import PreferenceOperations
from .constants import (
    FIXED_CATALOG_QUERY, FIXED_CATALOG_SOURCE, FIXED_CATALOG_ITEM_SOURCE,
    FIXED_CATALOG_VERSION, FIXED_CATALOG_CHUNK_SIZE, FIXED_CATALOG_MIN_IMAGE_BYTES,
    ORACLE_TAGS_SOURCE, ORACLE_TAGS_METADATA_URL,
)


class CardService(SearchOperations, ArtworkOperations, ImageOperations, CatalogSyncOperations,
                  PreferenceOperations, RulingsOperations, RulesOperations):
    """Shared dependencies and lifecycle for search, artwork, images, and sync.

    Internal groups call through self so subclass overrides and injected fetch
    functions remain effective across responsibilities.
    """
    def __init__(
        self,
        *,
        db_path: str | None = None,
        image_root: str | None = None,
        rulings_path: str | None = None,
        rules_path: str | None = None,
        fetch_json_fn: Callable[[str], dict] | None = None,
        fetch_bytes_fn: Callable[[str], bytes] | None = None,
        fetch_bulk_fn: Callable[[], list[dict]] | None = None,
    ):
        self.database = CardDatabase(db_path)
        # Explicit/test catalogs preserve their existing path ownership. The
        # default application service honors future wizard storage preferences.
        if db_path is None:
            from mtg_core.datasets import InstallationState
            state = InstallationState()
            configured_artwork = state.get('artwork_root')
            if configured_artwork:
                self.database.image_storage_root = Path(configured_artwork) / 'assets'
                image_root = image_root or configured_artwork
        self.rulings_path = rulings_path or str(
            Path(self.database.db_path).with_suffix('.rulings.sqlite3'))
        self.rules_path = rules_path or str(Path(self.database.db_path).with_suffix('.rules.sqlite3'))
        self.image_root = image_root or str(core_data_root() / "images")
        self.fetch_json_fn = fetch_json_fn or fetch_json
        self.fetch_bytes_fn = fetch_bytes_fn or fetch_bytes
        self.fetch_bulk_fn = fetch_bulk_fn
        self._printings_refreshed = {}


_DEFAULT_CARD_SERVICE: CardService | None = None


def get_default_card_service() -> CardService:
    global _DEFAULT_CARD_SERVICE
    if _DEFAULT_CARD_SERVICE is None:
        _DEFAULT_CARD_SERVICE = CardService()
    return _DEFAULT_CARD_SERVICE
