from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Callable

import deck_import
import high_res
from mtg_core import CardService, RemoteLookupUnavailable

from models import ProjectState, as_project_state
from . import high_res_service, project_service


@dataclass
class DeckImportWorkflowResult:
    state: ProjectState
    import_result: deck_import.ImportResult


@dataclass(frozen=True)
class ScryfallCardCandidate:
    name: str
    set_code: str | None
    set_name: str | None
    collector_number: str | None
    card_id: str | None
    oracle_id: str | None
    scryfall_id: str
    preview_url: str
    thumbnail_url: str
    filename: str
    art_context: high_res.CardContext
    card_data: dict
    image_asset_id: str | None = None
    backside_asset_id: str | None = None
    local_image_path: str | None = None
    search_source: str = "remote"


@dataclass(frozen=True)
class ScryfallCardSearchPage:
    candidates: list[ScryfallCardCandidate]
    total_count: int
    page_start: int
    page_size: int
    search_source: str = "remote"


@dataclass
class SingleCardImportWorkflowResult:
    state: ProjectState
    selected_card: ScryfallCardCandidate
    filename: str
    backside_filename: str | None
    art_candidate: high_res.HighResCandidate | None = None
    art_source: str | None = None


def import_decklist(*args, **kwargs):
    return deck_import.import_decklist(*args, **kwargs)


def import_archidekt_url(*args, **kwargs):
    return deck_import.import_archidekt_url(*args, **kwargs)


def read_decklist_file(path: str) -> str:
    return deck_import.read_decklist_file(path)


def is_archidekt_url(value: str) -> bool:
    return deck_import.is_archidekt_url(value)


def _front_face_name(card_data: dict) -> str:
    faces = card_data.get("card_faces") or []
    if faces:
        return faces[0].get("name") or card_data.get("name", "card")
    return card_data.get("name", "card")


def _extract_preview_urls(card_data: dict) -> tuple[str, str]:
    image_uris = card_data.get("image_uris")
    if image_uris:
        return (
            image_uris.get("normal") or image_uris.get("large") or image_uris.get("png") or "",
            image_uris.get("small") or image_uris.get("normal") or image_uris.get("large") or "",
        )

    for face in card_data.get("card_faces") or []:
        image_uris = face.get("image_uris")
        if image_uris:
            return (
                image_uris.get("normal") or image_uris.get("large") or image_uris.get("png") or "",
                image_uris.get("small") or image_uris.get("normal") or image_uris.get("large") or "",
            )
    return "", ""


def _build_card_candidate(card_service: CardService, result, search_source: str) -> ScryfallCardCandidate:
    card_data = result.payload
    face_urls = deck_import.extract_face_image_urls(card_data)
    front_name = _front_face_name(card_data)
    if len(face_urls) >= 2:
        filename = deck_import.build_face_image_filename(card_data, front_name, hidden=False)
    else:
        filename = deck_import.build_image_filename(card_data)

    preview_url, thumbnail_url = _extract_preview_urls(card_data)
    card_name = card_data.get("name") or front_name
    front_record = card_service.database.get_image_record(result.card_id, "default")
    back_record = card_service.database.get_image_record(result.card_id, "back")
    return ScryfallCardCandidate(
        name=card_name,
        set_code=card_data.get("set"),
        set_name=card_data.get("set_name"),
        collector_number=str(card_data.get("collector_number") or "") or None,
        card_id=result.card_id,
        oracle_id=result.oracle_id,
        scryfall_id=str(card_data.get("id") or filename),
        preview_url=preview_url,
        thumbnail_url=thumbnail_url,
        filename=filename,
        art_context=high_res.CardContext(
            filename=filename,
            query=card_name,
            display_name=card_name,
            set_code=card_data.get("set"),
            collector_number=str(card_data.get("collector_number") or "") or None,
        ),
        card_data=card_data,
        image_asset_id=None if front_record is None else front_record.asset_id,
        backside_asset_id=None if back_record is None else back_record.asset_id,
        local_image_path=card_service.get_image_path(result.card_id),
        search_source=search_source,
    )


def search_scryfall_card_page(
    name_query: str,
    set_filter: str | None = None,
    page_start: int = 0,
    page_size: int = 60,
    fetch_json: Callable[[str], dict] | None = None,
) -> ScryfallCardSearchPage:
    normalized_query = name_query.strip()
    if not normalized_query:
        raise ValueError("Enter a card name to search Scryfall.")

    card_service = _build_card_service(fetch_json)
    search_source = "local"
    local_results = card_service.search_cards(
        normalized_query,
        {"set_filter": set_filter, "allow_remote": False, "limit": 500},
    )
    results = list(local_results)
    should_try_remote = len(normalized_query) > 1 or not results
    if should_try_remote:
        try:
            remote_results = card_service.search_cards(
                normalized_query,
                {
                    "set_filter": set_filter,
                    "allow_remote": True,
                    "force_remote": True,
                    "raise_remote_unavailable": True,
                    "limit": 500,
                },
            )
            if remote_results:
                added_remote_result = False
                seen = {result.card_id for result in results}
                for result in remote_results:
                    if result.card_id in seen:
                        continue
                    seen.add(result.card_id)
                    results.append(result)
                    added_remote_result = True
                if added_remote_result:
                    search_source = "remote"
        except (RemoteLookupUnavailable, ValueError) as exc:
            if not results:
                if isinstance(exc, RemoteLookupUnavailable):
                    raise ValueError("No local matches are available offline. Connect to the internet to search Scryfall.") from exc
                raise
    filtered = [_build_card_candidate(card_service, result, search_source) for result in results]
    total_count = len(filtered)
    if page_start < 0:
        page_start = 0
    page_end = max(page_start, page_start + max(1, page_size))
    return ScryfallCardSearchPage(
        candidates=filtered[page_start:page_end],
        total_count=total_count,
        page_start=page_start,
        page_size=page_size,
        search_source=search_source,
    )


def apply_import_result(state: ProjectState, import_result: deck_import.ImportResult) -> ProjectState:
    state = as_project_state(state)
    for imported_card in import_result.imported:
        state.apply_imported_card(
            imported_card.filename,
            imported_card.entry.count,
            {
                "name": imported_card.entry.name,
                "set_code": imported_card.entry.set_code,
                "collector_number": imported_card.entry.collector_number,
            },
            card_id=imported_card.card_id,
            oracle_id=imported_card.oracle_id,
            image_asset_id=imported_card.image_asset_id,
            backside_asset_id=imported_card.backside_asset_id,
        )
    for front_name, back_name in import_result.backside_pairs.items():
        state.set_backside(front_name, back_name)
    return state


def import_into_project(
    state: ProjectState,
    img_dict: dict,
    image_dir: str,
    print_fn: Callable[[str], None],
    deck_text: str = "",
    archidekt_url: str = "",
    warn_fn: Callable[[str, str], None] | None = None,
) -> DeckImportWorkflowResult:
    state = as_project_state(state)
    if archidekt_url:
        import_result = deck_import.import_archidekt_url(
            archidekt_url,
            image_dir,
            print_fn,
        )
    else:
        import_result = deck_import.import_decklist(
            deck_text,
            image_dir,
            print_fn,
        )

    if import_result.imported:
        apply_import_result(state, import_result)
        print_fn("Refreshing project...")
        project_service.refresh_after_image_changes(state, img_dict, print_fn, warn_fn)

    return DeckImportWorkflowResult(state=state, import_result=import_result)


def import_single_card_into_project(
    state: ProjectState,
    img_dict: dict,
    image_dir: str,
    selected_card: ScryfallCardCandidate,
    print_fn: Callable[[str], None],
    warn_fn: Callable[[str, str], None] | None = None,
    art_candidate: high_res.HighResCandidate | None = None,
    art_source: str | None = None,
    backend_url: str = "",
    fetch_json: Callable[[str], dict] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
) -> SingleCardImportWorkflowResult:
    state = as_project_state(state)
    fetch_json = fetch_json or deck_import._fetch_json
    fetch_bytes = fetch_bytes or deck_import._fetch_bytes
    card_service = _build_card_service(fetch_json)

    entry = deck_import.DeckEntry(
        count=1,
        name=selected_card.name,
        set_code=selected_card.set_code,
        collector_number=selected_card.collector_number,
    )
    card_data = (
        dict(selected_card.card_data)
        if selected_card.card_data
        else (card_service.get_card(card_id=selected_card.card_id) if selected_card.card_id else None)
    )
    backside_name = None
    if selected_card.card_id and selected_card.image_asset_id and card_service.get_image_path(selected_card.card_id):
        if (card_data or {}).get("card_faces") and selected_card.backside_asset_id:
            face_names = [
                face.get("name") or selected_card.name
                for face in (card_data or {}).get("card_faces", [])
            ]
            if len(face_names) >= 2:
                backside_name = deck_import.build_face_image_filename(card_data, face_names[1], hidden=True)
        imported_card = deck_import.ImportedCard(
            entry=entry,
            filename=selected_card.filename,
            card_id=selected_card.card_id,
            oracle_id=selected_card.oracle_id,
            image_asset_id=selected_card.image_asset_id,
            backside_asset_id=selected_card.backside_asset_id,
        )
    else:
        card_data = card_data or deck_import.resolve_card(entry, fetch_json, card_service=card_service)
        imported_card, backside_name = deck_import.download_card_image_set(
            card_data,
            entry,
            image_dir,
            print_fn,
            fetch_bytes,
            card_service=card_service,
        )
    state.apply_imported_card(
        imported_card.filename,
        1,
        {
            "name": entry.name,
            "set_code": entry.set_code,
            "collector_number": entry.collector_number,
        },
        card_id=imported_card.card_id,
        oracle_id=imported_card.oracle_id,
        image_asset_id=imported_card.image_asset_id,
        backside_asset_id=imported_card.backside_asset_id,
    )
    if backside_name is not None:
        state.set_backside(imported_card.filename, backside_name)

    print_fn("Refreshing project...")
    project_service.refresh_after_image_changes(state, img_dict, print_fn, warn_fn)

    normalized_art_source = (art_source or getattr(art_candidate, "art_source", "") or "").strip() or None
    if art_candidate is not None:
        high_res_service.apply_candidate_to_project(
            state,
            img_dict,
            imported_card.filename,
            art_candidate,
            normalized_art_source or art_candidate.art_source,
            backend_url,
            print_fn,
            warn_fn,
        )

    return SingleCardImportWorkflowResult(
        state=state,
        selected_card=selected_card,
        filename=imported_card.filename,
        backside_filename=backside_name,
        art_candidate=art_candidate,
        art_source=normalized_art_source,
    )


def _build_card_service(fetch_json: Callable[[str], dict] | None = None) -> CardService:
    fetch_json = fetch_json or deck_import._fetch_json
    db_path = None
    if fetch_json is not deck_import._fetch_json:
        db_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".mtg_core_test_cache")
        os.makedirs(db_root, exist_ok=True)
        db_path = os.path.join(db_root, f"card_data_{uuid.uuid4().hex}.sqlite3")
    return CardService(db_path=db_path, fetch_json_fn=fetch_json)
