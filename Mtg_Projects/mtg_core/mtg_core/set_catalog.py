"""Set discovery and bounded catalog reads; no printing or widget dependencies."""

from dataclasses import dataclass
from contextlib import closing
from urllib.parse import quote


@dataclass(frozen=True)
class SetInfo:
    code: str
    name: str
    released_at: str = ""
    available: int = 0
    expected: int | None = None
    parent: str = ""
    kind: str = ""
    symbol_url: str = ""


def discover_sets(service, *, online=False):
    with closing(service.database.connect()) as db:
        rows = db.execute("""SELECT lower(set_code) code, max(set_name) name,
            min(released_at) released_at, count(DISTINCT coalesce(nullif(oracle_id, ''), name)) available
            FROM prints WHERE coalesce(set_code, '') != '' GROUP BY lower(set_code)""").fetchall()
    local = {
        r["code"]: SetInfo(
            r["code"],
            r["name"] or r["code"].upper(),
            r["released_at"] or "",
            r["available"],
        )
        for r in rows
    }
    notice = ""
    if online:
        try:
            for item in service.fetch_json_fn("https://api.scryfall.com/sets")["data"]:
                code = item["code"].lower()
                local[code] = SetInfo(
                    code,
                    item["name"],
                    item.get("released_at", ""),
                    local[code].available if code in local else 0,
                    item.get("card_count"),
                    item.get("parent_set_code", ""),
                    item.get("set_type", ""),
                    item.get("icon_svg_uri", ""),
                )
        except Exception:
            from mtg_core.diagnostics import get_logger

            get_logger(__name__).exception("Set directory unavailable")
            notice = "The online set list is unavailable. Showing sets in your local catalog. Try again to refresh."
    return sorted(
        local.values(), key=lambda s: (s.released_at, s.name), reverse=True
    ), notice


def filter_sets(sets, query):
    words = query.casefold().split()
    return [s for s in sets if all(w in f"{s.name} {s.code}".casefold() for w in words)]


def load_set_cards(service, codes):
    codes = sorted({code.lower() for code in codes})
    if not codes:
        return []
    with closing(service.database.connect()) as db:
        rows = db.execute(
            "SELECT * FROM prints WHERE lower(set_code) IN ("
            + ",".join("?" for _ in codes)
            + ") ORDER BY collector_number, card_id",
            codes,
        ).fetchall()
    result = []
    for row in rows:
        record = service.database.row_to_print_record(row)
        payload = dict(record.payload)
        for key, value in (
            ("id", record.card_id),
            ("oracle_id", record.oracle_id),
            ("name", record.name),
            ("set", record.set_code),
            ("collector_number", record.collector_number),
        ):
            if not payload.get(key):
                payload[key] = value
        result.append(payload)
    return result


def download_set_data(
    service, code, *, cancelled=lambda: False, progress=lambda _: None
):
    """Incremental upserts are safe to retain on interruption and retry."""
    url = (
        "https://api.scryfall.com/cards/search?unique=prints&include_extras=true&q="
        + quote("set:" + code)
    )
    prepared = 0
    while url:
        if cancelled():
            return False
        progress("Updating available cards")
        page = service.fetch_json_fn(url)
        if page.get("has_more") and not page.get("next_page"):
            raise ValueError("The set update did not include all pages.")
        for payload in page["data"]:
            if cancelled():
                return False
            service.database.upsert_card_payload(payload)
            prepared += 1
            if prepared % 50 == 0:
                progress(f"Updating available cards · {prepared} prepared")
        url = page.get("next_page") if page.get("has_more") else None
    return True


def set_artwork_favorites(service, payloads):
    identities = sorted({p["oracle_id"] for p in payloads if p.get("oracle_id")})
    result = {}
    with closing(service.database.connect()) as db:
        for offset in range(0, len(identities), 400):
            batch = identities[offset : offset + 400]
            rows = db.execute(
                "SELECT oracle_id, card_id FROM artwork_favorites WHERE oracle_id IN ("
                + ",".join("?" for _ in batch)
                + ")",
                batch,
            )
            result.update((r["oracle_id"], r["card_id"]) for r in rows)
    return result
