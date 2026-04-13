from __future__ import annotations

import json
import urllib.parse
import urllib.error
import urllib.request


USER_AGENT = "print-proxy-prep/1.0"


class RemoteLookupUnavailable(OSError):
    """Raised when a remote lookup cannot be completed because the network is unavailable."""


def _decode_error_payload(error: urllib.error.HTTPError) -> dict | None:
    try:
        payload = error.read()
    except OSError:
        return None
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def is_no_card_match_error(details: str | None) -> bool:
    normalized = (details or "").casefold()
    return (
        "no cards found" in normalized
        or "didn't match any cards" in normalized
        or "did not match any cards" in normalized
        or "your query didn't match" in normalized
        or "your query did not match" in normalized
    )


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        payload = _decode_error_payload(error)
        if payload is not None:
            if payload.get("object") == "error":
                raise ValueError(payload.get("details", "Scryfall error")) from error
            return payload
        raise ValueError(f"Remote lookup failed with HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RemoteLookupUnavailable("Internet connection unavailable for remote card lookup.") from error
    if payload.get("object") == "error":
        raise ValueError(payload.get("details", "Scryfall error"))
    return payload


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.URLError as error:
        raise RemoteLookupUnavailable("Internet connection unavailable for remote image download.") from error


def build_named_url(exact_name: str) -> str:
    return "https://api.scryfall.com/cards/named?" + urllib.parse.urlencode(
        {"exact": exact_name}
    )


def build_set_collectornumber_url(set_code: str, collector_number: str) -> str:
    return (
        "https://api.scryfall.com/cards/"
        f"{urllib.parse.quote(set_code)}/{urllib.parse.quote(collector_number)}"
    )


def build_exact_print_search_url(name: str, set_code: str) -> str:
    query = f'!"{name}" set:{set_code}'
    return "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode(
        {"q": query, "unique": "prints"}
    )


def build_print_search_url(query: str, *, include_extras: bool = False) -> str:
    params = {"q": query, "unique": "prints"}
    if include_extras:
        params["include"] = "extras"
    return "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode(
        params
    )


def extract_image_urls(card_data: dict) -> tuple[str | None, str | None, str | None]:
    image_uris = card_data.get("image_uris")
    if image_uris:
        return (
            image_uris.get("png") or image_uris.get("large") or image_uris.get("normal"),
            image_uris.get("small") or image_uris.get("normal") or image_uris.get("large"),
            image_uris.get("normal") or image_uris.get("large") or image_uris.get("png"),
        )

    for face in card_data.get("card_faces") or []:
        image_uris = face.get("image_uris")
        if image_uris:
            return (
                image_uris.get("png") or image_uris.get("large") or image_uris.get("normal"),
                image_uris.get("small") or image_uris.get("normal") or image_uris.get("large"),
                image_uris.get("normal") or image_uris.get("large") or image_uris.get("png"),
            )
    return None, None, None


def iter_search_payloads(query: str, fetch_json_fn=fetch_json, *, include_extras: bool = False) -> list[dict]:
    url = build_print_search_url(query, include_extras=include_extras)
    payloads: list[dict] = []
    seen_ids: set[str] = set()
    while url:
        try:
            payload = fetch_json_fn(url)
        except ValueError as exc:
            if is_no_card_match_error(str(exc)):
                return []
            raise
        if payload.get("object") == "error":
            details = payload.get("details")
            if is_no_card_match_error(details):
                return []
            raise ValueError(details or "Scryfall card search failed.")
        if payload.get("object") != "list":
            raise ValueError("Scryfall card search failed.")
        for card_data in payload.get("data") or []:
            card_id = str(card_data.get("id") or "")
            if card_id and card_id in seen_ids:
                continue
            if card_id:
                seen_ids.add(card_id)
            payloads.append(card_data)
        url = payload.get("next_page") if payload.get("has_more") else None
    return payloads


def resolve_card_payload(
    *,
    exact_name: str | None = None,
    set_code: str | None = None,
    collector_number: str | None = None,
    card_id: str | None = None,
    fetch_json_fn=fetch_json,
) -> dict:
    if card_id:
        return fetch_json_fn(f"https://api.scryfall.com/cards/{urllib.parse.quote(card_id)}")
    if set_code and collector_number:
        return fetch_json_fn(build_set_collectornumber_url(set_code, collector_number))
    if set_code and exact_name:
        payload = fetch_json_fn(build_exact_print_search_url(exact_name, set_code))
        if payload.get("object") == "list" and payload.get("data"):
            return payload["data"][0]
        raise ValueError("Card not found")
    if exact_name:
        return fetch_json_fn(build_named_url(exact_name))
    raise ValueError("A card lookup requires exact_name, card_id, or set+collector number.")


def search_prints_payloads(
    name_query: str,
    fetch_json_fn=fetch_json,
    *,
    include_extras: bool = False,
    exact_first: bool = True,
) -> list[dict]:
    normalized_query = (name_query or "").strip()
    if not normalized_query:
        return []
    if exact_first:
        exact_query = f'!"{normalized_query}"'
        payloads = iter_search_payloads(exact_query, fetch_json_fn, include_extras=include_extras)
        if payloads:
            return payloads
    return iter_search_payloads(normalized_query, fetch_json_fn, include_extras=include_extras)
