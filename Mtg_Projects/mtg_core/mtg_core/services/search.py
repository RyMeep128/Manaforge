"""Internal search operations for CardService."""
from __future__ import annotations

from dataclasses import replace
import time
from mtg_core.models import PrintRecord, SearchCardResult
from mtg_core.sync import RemoteLookupUnavailable, iter_search_payloads, resolve_card_payload, search_prints_payloads


def _parse_token_search_query(query: str) -> tuple[str, bool]:
    stripped = (query or "").strip()
    parts = stripped.split()
    if parts and parts[-1].casefold() == "token":
        return " ".join(parts[:-1]).strip(), True
    return stripped, False


def _search_result_from_row(row: PrintRecord) -> SearchCardResult:
    return SearchCardResult(
        card_id=row.card_id,
        oracle_id=row.oracle_id,
        name=row.name,
        set_code=row.set_code,
        set_name=row.set_name,
        collector_number=row.collector_number,
        preview_url=row.preview_url,
        thumbnail_url=row.thumbnail_url,
        payload=row.payload,
    )


def _build_token_remote_query(query: str) -> str:
    stripped = (query or "").strip()
    return f"t:token {stripped}".strip()


def _filter_print_rows(rows: list[PrintRecord], set_filter: str) -> list[PrintRecord]:
    if not set_filter:
        return list(rows)
    filtered: list[PrintRecord] = []
    for row in rows:
        row_set_code = (row.set_code or "").casefold()
        row_set_name = (row.set_name or "").casefold()
        if row_set_code == set_filter or set_filter in row_set_name:
            filtered.append(row)
    return filtered


class SearchOperations:
    """Operation group sharing the facade dependencies; not instantiated alone."""

    def search_cards(self, query: str, filters: dict | None = None) -> list[SearchCardResult]:
        filters = filters or {}
        if filters.get("scryfall_syntax", False):
            search_query = (query or "").strip()
            token_mode = False
        else:
            search_query, token_mode = _parse_token_search_query(query)
        set_filter = (filters.get("set_filter") or "").strip().casefold()
        scryfall_syntax = bool(filters.get("scryfall_syntax", False))
        limit = max(1, int(filters.get("limit", 200)))
        online_mode = bool(filters.get("online_mode", False))
        cache_ttl_seconds = max(1, int(filters.get("cache_ttl_seconds", 60 * 60)))
        if scryfall_syntax:
            from mtg_core.search.syntax import LocalQueryError
            try:
                local_rows = self.database.search_syntax(search_query, limit=limit,
                    offset=max(0, int(filters.get('offset', 0))),
                    set_filter=set_filter, online_mode=online_mode,
                    should_cancel=filters.get('should_cancel'))
            except LocalQueryError:
                if not filters.get('allow_remote', True):
                    raise
                local_rows = []
        else:
            local_rows = self.database.search_prints(
                search_query, limit=limit, token_mode=token_mode,
                online_mode=online_mode, cache_ttl_seconds=cache_ttl_seconds)
        filtered_rows = _filter_print_rows(local_rows, set_filter)
        if scryfall_syntax and filters.get("allow_remote", True):
            remote_query = search_query
            if set_filter:
                remote_query = f"({remote_query}) set:{set_filter}"
            try:
                payloads = search_prints_payloads(
                    remote_query,
                    self.fetch_json_fn,
                    include_extras=True,
                    exact_first=False,
                )
                cache_expires_at = time.time() + cache_ttl_seconds if online_mode else None
                remote_rows = []
                for payload in payloads[:limit]:
                    self.database.upsert_card_payload(
                        payload,
                        cache_scope="online_search" if online_mode else None,
                        cache_expires_at=cache_expires_at,
                    )
                    row = self.database.get_print_by_card_id(str(payload.get("id") or ""))
                    if row is not None:
                        remote_rows.append(row)
                filtered_rows = _filter_print_rows(remote_rows, set_filter)
            except RemoteLookupUnavailable:
                if filters.get("raise_remote_unavailable") or not filtered_rows:
                    raise
            return [_search_result_from_row(row) for row in filtered_rows[:limit]]
        if (
            (filters.get("force_remote", False) or not filtered_rows)
            and filters.get("allow_remote", True)
        ):
            try:
                remote_query = _build_token_remote_query(search_query) if token_mode else search_query
                cache_expires_at = time.time() + cache_ttl_seconds if online_mode else None
                for payload in search_prints_payloads(
                    remote_query,
                    self.fetch_json_fn,
                    include_extras=token_mode,
                    exact_first=not token_mode,
                ):
                    self.database.upsert_card_payload(
                        payload,
                        cache_scope="online_search" if online_mode else None,
                        cache_expires_at=cache_expires_at,
                    )
            except RemoteLookupUnavailable:
                if filters.get("raise_remote_unavailable") or not filtered_rows:
                    raise
            local_rows = self.database.search_prints(
                search_query,
                limit=limit,
                token_mode=token_mode,
                online_mode=online_mode,
                cache_ttl_seconds=cache_ttl_seconds,
            )
            filtered_rows = _filter_print_rows(local_rows, set_filter)
        return [_search_result_from_row(row) for row in filtered_rows]

    def search_editor_cards(self, query, *, should_cancel=None):
        """Local editor search with role evidence and cooperative cancellation."""
        from mtg_core.categorization import classify
        from mtg_core.search.cancellation import check_cancelled
        check_cancelled(should_cancel)
        results = self.search_cards(query, {
            'scryfall_syntax': True, 'allow_remote': False, 'limit': 100,
            'should_cancel': should_cancel})
        check_cancelled(should_cancel)
        data = self.database.categorization_data(
            [], [r.oracle_id for r in results], should_cancel=should_cancel)
        enriched = []
        for result in results:
            check_cancelled(should_cancel)
            enriched.append(replace(result, payload={**(result.payload or {}),
                '_category_evidence': classify(result.payload or {}, data['tags'].get(result.oracle_id, []))}))
        return enriched

    def analyze_entries(self, entries):
        """Return explainable role proposals without mutating entries or global tags.

        Reads are batched and local; GUI callers should run this in a worker.
        """
        from mtg_core.categorization import analyze_entries
        return analyze_entries(self.database, entries)

    def get_deck_legality_data(self, entries):
        """Load dated local facts for deck checks, preserving missing-data signals."""
        return self.database.legality_data([entry.card_id for entry in entries if entry.card_id])

    def get_oracle_tags(self, oracle_id):
        """Return local Oracle tags for display; never synchronize implicitly."""
        return self.database.oracle_tags_for_card(oracle_id) if oracle_id else []

    def get_card(
        self,
        *,
        exact_name: str | None = None,
        oracle_id: str | None = None,
        card_id: str | None = None,
    ) -> dict | None:
        record: PrintRecord | None = None
        if card_id:
            record = self.database.get_print_by_card_id(card_id)
        elif oracle_id:
            record = self.database.get_canonical_print(oracle_id)
        elif exact_name:
            record = self.database.get_named_print(exact_name)
        return None if record is None else dict(record.payload)

    def get_print(self, *, set_code: str, collector_number: str) -> dict | None:
        record = self.database.get_print_by_set_and_number(set_code, collector_number)
        return None if record is None else dict(record.payload)

    def get_prints(self, oracle_id: str, *, allow_remote: bool = False) -> list[dict]:
        if allow_remote and time.monotonic() - self._printings_refreshed.get(oracle_id, float('-inf')) > 3600:
            payloads = iter_search_payloads(f'oracleid:{oracle_id}', self.fetch_json_fn, include_extras=True)
            for payload in payloads:
                if payload.get('oracle_id') == oracle_id and payload.get('id'):
                    self.database.upsert_card_payload(payload)
            self._printings_refreshed[oracle_id] = time.monotonic()
        return [dict(row.payload) for row in self.database.get_prints_for_oracle(oracle_id)]

    def get_canonical_print(self, oracle_id: str) -> dict | None:
        record = self.database.get_canonical_print(oracle_id)
        return None if record is None else dict(record.payload)

    def fetch_missing_card(
        self,
        *,
        exact_name: str | None = None,
        set_code: str | None = None,
        collector_number: str | None = None,
        card_id: str | None = None,
    ) -> dict:
        payload = resolve_card_payload(
            exact_name=exact_name,
            set_code=set_code,
            collector_number=collector_number,
            card_id=card_id,
            fetch_json_fn=self.fetch_json_fn,
        )
        return dict(self.database.upsert_card_payload(payload).payload)
