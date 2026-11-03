"""Capture a real packaged public saved-deck acceptance match before owned cleanup.

Uses the existing opt-in driver. This command makes strategic fixture choices;
normal Manaforge launches never mount that driver. Images remain local artifacts.
"""

import importlib.util
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
spec = importlib.util.spec_from_file_location(
    "game_acceptance", ROOT / "tools/check_play_unity_game.py"
)
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def main():
    output = ROOT / (
        "Mtg_Projects/mtg_play_unity/Artifacts/ArenaVisualReview-"
        + uuid.uuid4().hex[:8]
    )
    original = acceptance.LiveGameLaunch

    class CaptureLaunch(original):
        def close(self):
            if self.root and Path(self.root).is_dir():
                output.mkdir(parents=True, exist_ok=True)
                for path in Path(self.root).iterdir():
                    if path.suffix == ".png" or path.name in (
                        "board-input-proof.json",
                        "resolution-proof.json",
                    ):
                        shutil.copy2(path, output / path.name)
            super().close()

    acceptance.LiveGameLaunch = CaptureLaunch
    # Resolve fixture printing identities through Core, never by a visual/name guess.
    # The exact set/collector identity is also validated by native launch admission.
    from mtg_core.services import CardService

    def offline(*args, **kwargs):
        raise RuntimeError("VISUAL_REVIEW_NETWORK_FORBIDDEN")

    service = CardService(
        fetch_json_fn=offline, fetch_bytes_fn=offline, fetch_bulk_fn=offline
    )
    original_deck = acceptance.public_deck

    def public_deck(ai=False):
        document = original_deck(ai)
        for entry in document.deck.entries:
            card = service.get_print(
                set_code=entry.set_code.lower(), collector_number=entry.collector_number
            )
            if card:
                entry.card_id = card["id"]
                entry.oracle_id = card["oracle_id"]
        return document

    acceptance.public_deck = public_deck
    sys.argv = [sys.argv[0], "--public-decks", "--output", str(output)]
    return acceptance.main()


if __name__ == "__main__":
    raise SystemExit(main())
