import hashlib
import json
from mtg_play.live_game import prepare_local_artwork
from mtg_play.tests.test_visual_catalog import Service, card


def test_local_launch_artwork_uses_only_requested_ids_and_preserves_missing_fallback(
    tmp_path,
):
    class Recording(Service):
        def get_card(self, *args, **kwargs):
            seen.append(kwargs.get("card_id"))
            return super().get_card(*args, **kwargs)

    seen = []
    document = {"deck": {"entries": [{"card_id": "selected"}, {"card_id": "selected"}]}}
    directory, pin = prepare_local_artwork(
        document,
        tmp_path,
        "session",
        "viewer",
        Recording(card("selected", type_line="Creature")),
    )
    payload = (tmp_path / "artwork/manifest.json").read_bytes()
    manifest = json.loads(payload)
    assert pin == hashlib.sha256(payload).hexdigest()
    assert manifest["session_id"] == "session" and manifest["viewer_id"] == "viewer"
    assert manifest["entries"] == []
    assert len(manifest["unavailable"]) == 1
    assert set(seen) == {"selected"}
    assert directory == str((tmp_path / "artwork").resolve())


def test_empty_local_deck_does_not_require_core_or_create_assets(tmp_path):
    assert prepare_local_artwork({"deck": {"entries": []}}, tmp_path, "s", "v") == (
        None,
        None,
    )
    assert list(tmp_path.iterdir()) == []
