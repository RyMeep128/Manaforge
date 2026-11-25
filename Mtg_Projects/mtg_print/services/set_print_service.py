"""Prepare a complete ordinary print project before publishing it to the library."""

import tempfile
import io
import os
from PIL import Image

from mtg_core.decklists import DecklistEntry
from mtg_print import card_layouts, deck_import, library
from mtg_print.models import ProjectState
from mtg_print.set_inventory import inventory


class SetPrintCancelled(Exception):
    pass


class SetPrintError(ValueError):
    """An actionable message safe to display without internal exception details."""


def generate_project(
    service,
    set_info,
    cards,
    settings,
    *,
    cancelled=lambda: False,
    progress=lambda text, value, maximum: None,
    defaults=None,
    fetch_bytes=None,
):
    selected = [(card, count) for card, count in inventory(cards, settings) if count]
    if not selected:
        raise SetPrintError("Choose at least one card to print.")

    def check():
        if cancelled():
            raise SetPrintCancelled()

    check()
    progress("Preparing your cards", 0, len(selected))
    state = ProjectState.from_dict(
        defaults if defaults is not None else library._initial_project_dict(None)
    )
    state.set_print_config = dict(
        version=1, set_code=set_info.code, **settings.to_dict()
    )
    # Downloads use the shared asset store. Temporary compatibility files are
    # discarded; no draft, existing project, or artwork cache is replaced.
    with tempfile.TemporaryDirectory(prefix="manaforge-set-") as staging:

        def fetch(url):
            check()
            cached_id = service.database.find_image_asset_by_url(url)
            cached = service.database.get_image_asset(cached_id) if cached_id else None
            if cached and cached.payload:
                try:
                    with Image.open(io.BytesIO(cached.payload)) as decoded:
                        decoded.verify()
                except (OSError, ValueError):
                    cached = None
            result = (
                cached.payload
                if cached and cached.payload
                else (fetch_bytes or deck_import._fetch_bytes)(url)
            )
            check()
            # Validate before the importer registers anything in the shared cache.
            with Image.open(io.BytesIO(result)) as decoded:
                decoded.verify()
            return result

        for index, (card, count) in enumerate(selected):
            check()
            progress("Finding card artwork", index, len(selected))
            entry = DecklistEntry(
                count, card["name"], card.get("set"), card.get("collector_number")
            )
            try:
                front = service.database.get_image_record(card["id"], "default")
                back_record = service.database.get_image_record(card["id"], "back")
                double = card_layouts.has_printed_back(card)
                if (
                    front
                    and service.get_image_path(card["id"], "default")
                    and (
                        not double
                        or (back_record and service.get_image_path(card["id"], "back"))
                    )
                ):
                    faces = card.get("card_faces") or []
                    filename = (
                        deck_import.build_face_image_filename(card, faces[0]["name"])
                        if double and faces
                        else deck_import.build_image_filename(card)
                    )
                    back = (
                        deck_import.build_face_image_filename(
                            card, faces[1]["name"], hidden=True
                        )
                        if double and len(faces) >= 2
                        else None
                    )
                    if double and not back:
                        raise ValueError("Both face names are needed.")
                    imported = deck_import.ImportedCard(
                        entry,
                        filename,
                        card["id"],
                        card.get("oracle_id"),
                        front.asset_id,
                        back_record.asset_id if double else None,
                    )
                else:
                    if double and len(deck_import.extract_face_image_urls(card)) < 2:
                        raise ValueError("Artwork for both faces is needed.")
                    imported, back = deck_import.download_card_image_set(
                        card,
                        entry,
                        staging,
                        lambda _: check(),
                        fetch,
                        card_service=service,
                    )
                for asset_id in (imported.image_asset_id, imported.backside_asset_id):
                    if asset_id:
                        asset = service.database.get_image_asset(asset_id)
                        with Image.open(io.BytesIO(asset.payload)) as decoded:
                            decoded.verify()
            except SetPrintCancelled:
                raise
            except Exception as exc:
                raise SetPrintError(
                    f"Artwork for {card['name']} could not be prepared. Check your connection and retry, or exclude this card in Review cards."
                ) from exc
            filename = imported.filename
            if filename in state.cards:
                stem, extension = os.path.splitext(filename)
                filename = f"{stem}__{card['id']}{extension}"
            if back and back in state.backsides.values():
                stem, extension = os.path.splitext(back)
                back = f"{stem}__{card['id']}{extension}"
            state.apply_imported_card(
                filename,
                count,
                {
                    "name": card["name"],
                    "set_code": card.get("set"),
                    "collector_number": card.get("collector_number"),
                    "rarity": card.get("rarity"),
                },
                card_id=imported.card_id,
                oracle_id=imported.oracle_id,
                image_asset_id=imported.image_asset_id,
                backside_asset_id=imported.backside_asset_id,
            )
            if back:
                state.set_backside(filename, back)
                state.backside_enabled = True
        check()
        progress("Organizing print sheets", len(selected), len(selected))
        suffix = "-".join(
            str(settings.quantities[r])
            for r in ("common", "uncommon", "rare", "mythic")
        )
        name = f"{set_info.name} — {settings.preset}"
        if settings.preset != "One of Each":
            name += f" ({suffix})"
        result = library.create_project(name, prepared_state=state)
    progress("Your project is ready", len(selected), len(selected))
    return result
