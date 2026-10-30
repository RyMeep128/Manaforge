"""Frozen local printing references prepared before a match; no network APIs."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .artwork_cache import local_source, read_local_image, RENDER_VERSION


@dataclass(frozen=True)
class MatchAssets:
    sources: tuple  # (printing, variant, absolute path, SHA-256)
    layouts: tuple  # (printing, layout)
    missing: tuple[str, ...]

    def image_service(self):
        return FrozenImages(self)


class FrozenImages:
    def __init__(self, manifest):
        self.manifest = manifest

    def get_card(self, *, card_id):
        return {"layout": dict(self.manifest.layouts).get(card_id)}

    def get_image_path(self, card_id, variant="default"):
        for printing, face_variant, path, digest in self.manifest.sources:
            if (printing, face_variant) == (card_id, variant):
                try:
                    return (
                        path
                        if hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                        else None
                    )
                except OSError:
                    return None
        return None  # New/generated objects use placeholders, never live fallbacks.


def prepare_assets(documents, service, *, cancel, report):
    sources, layouts, missing, seen = [], [], [], set()
    entries = [
        entry
        for document in documents
        for entry in document.deck.entries
        if entry.section not in {"considering", "excluded", "display_commander"}
        and entry.quantity > 0
    ]
    for index, entry in enumerate(entries):
        if cancel.is_set():
            return None
        report({"stage": "match_artwork", "current": index + 1, "total": len(entries)})
        printing = entry.card_id
        identity = printing or ("missing", entry.name)
        if identity in seen:
            continue
        seen.add(identity)
        label = entry.name or "Unnamed card"
        if not printing:
            missing.append(label)
            continue
        try:
            payload = service.get_card(card_id=printing) or {}
        except Exception:
            payload = {}
        layout = payload.get("layout")
        layouts.append((printing, layout))
        faces = (
            (0, 1)
            if layout
            in {
                "transform",
                "modal_dfc",
                "reversible_card",
                "double_faced_token",
                "flip",
            }
            else (0,)
        )
        for face in faces:
            if cancel.is_set():
                return None
            try:
                path, flip = local_source(service, printing, face)
                if path is None:
                    raise OSError()
                variant = "default" if not face or flip else f"face-{face}"
                reference = (
                    printing,
                    variant,
                    str(path.resolve()),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                # Decode and generate from the same frozen source used by gameplay.
                provisional = MatchAssets(
                    tuple(sources + [reference]), tuple(layouts), ()
                )
                image = read_local_image(
                    provisional.image_service(),
                    (printing, None, 300, face, RENDER_VERSION),
                )
                if image.isNull():
                    raise OSError()
                if reference not in sources:
                    sources.append(reference)
            except Exception:
                missing.append(label + (" (alternate face)" if face else ""))
    return MatchAssets(tuple(sources), tuple(layouts), tuple(dict.fromkeys(missing)))
