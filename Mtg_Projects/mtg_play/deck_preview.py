"""One-time offline deck preview, never gameplay state or an all-seats manifest."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import uuid
from .artwork_bundle import export_artwork_bundle
from .launch_lifecycle import LaunchOwner, LaunchLifecycleError
from .visual_catalog import collect_visual_candidates

MAX_CARDS = 24
MAX_MANIFEST = 1024 * 1024
DEFAULT_PLAYER = (
    Path(__file__).resolve().parents[1]
    / "mtg_play_unity/Builds/Windows/ManaforgePlay.exe"
)


class PreviewError(ValueError):
    pass


def text(value, maximum=16384):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(ord(c) < 32 and c not in "\n\t\r" for c in value)
    ):
        raise PreviewError("PREVIEW_INVALID_DECK")
    return value


def project_deck(document, format, service):
    if (
        format not in ("freeform", "commander")
        or not 1 <= len(document.deck.entries) <= 2048
    ):
        raise PreviewError("PREVIEW_INVALID_DECK")
    rows, seen = [], set()
    for entry in document.deck.entries:
        identity = text(entry.entry_id, 128)
        if (
            not identity
            or identity in seen
            or type(entry.quantity) is not int
            or not 1 <= entry.quantity <= 10000
        ):
            raise PreviewError("PREVIEW_INVALID_DECK")
        seen.add(identity)
    for entry in sorted(
        document.deck.entries, key=lambda e: (e.sort_order, e.entry_id)
    )[:MAX_CARDS]:
        printing, oracle = text(entry.card_id, 1024), text(entry.oracle_id, 1024)
        metadata = service.get_card(card_id=printing) if printing else None
        if (
            not isinstance(metadata, dict)
            or metadata.get("id") != printing
            or not metadata.get("oracle_id")
            or (oracle and metadata.get("oracle_id") != oracle)
        ):
            metadata = {}
        faces = metadata.get("card_faces")
        face = (
            faces[0]
            if isinstance(faces, list) and faces and isinstance(faces[0], dict)
            else metadata
        )
        rows.append(
            dict(
                entry_id=entry.entry_id,
                quantity=entry.quantity,
                section=text(str(entry.section), 128),
                oracle_id=oracle or text(metadata.get("oracle_id"), 1024),
                printing_id=printing,
                artwork_printing_id=printing,
                name=text(face.get("name") or entry.name or "Unnamed card", 1024),
                mana_cost=text(face.get("mana_cost")),
                type_line=text(face.get("type_line")),
                rules_text=text(face.get("oracle_text")),
                power=text(face.get("power")),
                toughness=text(face.get("toughness")),
                loyalty=text(face.get("loyalty")),
                defense=text(face.get("defense")),
            )
        )
    return dict(
        deck_preview_version=1,
        mode="deck_preview",
        deck_name=text(document.deck.name or "Saved deck", 1024),
        format=format,
        total_entries=len(document.deck.entries),
        cards=rows,
    )


def prepare_preview(document, format, service, root):
    root = Path(root)
    preview = project_deck(document, format, service)
    scope = uuid.uuid4().hex
    for row in preview["cards"]:
        if not row["printing_id"] or not row["oracle_id"]:
            row["artwork_printing_id"] = None
            continue
        try:
            candidates = collect_visual_candidates(
                service, row["printing_id"], 0, max_cached_candidates=2
            )
            compatible = next(
                (
                    c
                    for c in candidates
                    if c.cached and c.standard_compatible and c.face_index == 0
                ),
                None,
            )
            if compatible is not None and compatible.oracle_id == row["oracle_id"]:
                row["artwork_printing_id"] = compatible.printing_id
        except ValueError:
            row["artwork_printing_id"] = None
    ids = tuple(
        dict.fromkeys(
            row["artwork_printing_id"]
            for row in preview["cards"]
            if row["artwork_printing_id"] and row["oracle_id"]
        )
    )
    _, artwork_pin = export_artwork_bundle(
        service,
        ids,
        root / "artwork",
        session_id=scope,
        viewer_id="deck-preview",
        max_asset_bytes=64 * 1024 * 1024,
        preview_only=True,
    )
    payload = json.dumps(preview, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(payload) > MAX_MANIFEST:
        raise PreviewError("PREVIEW_TOO_LARGE")
    (root / "deck.json").write_bytes(payload)
    return json.dumps(
        dict(
            deck_preview_version=1,
            mode="deck_preview",
            directory=str(root.resolve()),
            deck_sha256=hashlib.sha256(payload).hexdigest(),
            artwork_sha256=artwork_pin,
            preview_id=scope,
        ),
        separators=(",", ":"),
    ).encode("utf-8")


class PreviewLaunch:
    """Retains the existing process owner and its ephemeral assets for cleanup retries."""

    def __init__(self, owner=None):
        self.owner = owner or LaunchOwner(startup_timeout=120)
        self.root = None

    def close(self):
        if not self.owner.close().confirmed:
            raise PreviewError("PREVIEW_CLEANUP_UNCONFIRMED")
        if self.root is None:
            return
        resolved = self.root.resolve()
        if (
            resolved != self.root
            or resolved.parent != Path(tempfile.gettempdir()).resolve()
            or not resolved.name.startswith("manaforge-deck-preview-")
            or self.root.is_symlink()
        ):
            raise PreviewError("PREVIEW_FILES_CLEANUP_FAILED")
        try:
            if resolved.exists():
                shutil.rmtree(resolved)
        except OSError:
            raise PreviewError("PREVIEW_FILES_CLEANUP_FAILED") from None
        self.root = None


def run_preview(
    document,
    format,
    service,
    cancel,
    report,
    *,
    player=DEFAULT_PLAYER,
    owner=None,
    launch=None,
):
    """Blocking launch worker. Only a fresh owned directory and child may be cleaned up."""
    player = Path(player).resolve()
    if not player.is_file():
        raise PreviewError("PREVIEW_BUILD_MISSING")
    launch = launch or PreviewLaunch(owner)
    owner = launch.owner
    root = launch.root = Path(tempfile.mkdtemp(prefix="manaforge-deck-preview-"))
    try:
        if cancel.is_set():
            return "cancelled"
        report(dict(phase="Preparing cached deck artwork"))
        payload = prepare_preview(document, format, service, root)
        if cancel.is_set():
            return "cancelled"
        owner.start_preview(
            [
                str(player),
                "-manaforgeDeckPreview",
                "1",
                "-screen-fullscreen",
                "0",
                "-screen-width",
                "1366",
                "-screen-height",
                "768",
                "-logFile",
                "NUL",
            ],
            cwd=str(player.parent),
            preview_bootstrap=payload,
        )
        ready = False
        while True:
            if cancel.wait(0.05):
                owner.request_cancel()
                return "cancelled"
            exited = owner.client_exit_code
            if exited is not None:
                if not ready or exited != 0:
                    raise PreviewError("PREVIEW_PLAYER_FAILED")
                return "closed"
            if not ready and (root / "preview-ready.json").is_file():
                path = root / "preview-ready.json"
                if (
                    path.stat().st_size > 128
                    or path.read_bytes() != b'{"deck_preview_version":1,"ready":true}'
                ):
                    raise PreviewError("PREVIEW_STARTUP_INVALID")
                owner.client_ready()
                ready = True
                report(dict(phase="Deck Preview — Not a Live Game"))
            owner.check_health()
    except LaunchLifecycleError as error:
        raise PreviewError(error.code) from None
    except PreviewError:
        raise
    except Exception:
        raise PreviewError("PREVIEW_PREPARATION_FAILED") from None
    finally:
        launch.close()
