"""Real packaged 1vAI artwork proof: mixed Mountain arts, opponent cards and Goblin tokens."""

import argparse
import json
from pathlib import Path
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
from mtg_core.decks import Deck, DeckDocument, DeckEntry  # noqa: E402
from mtg_core.services import CardService  # noqa: E402
from mtg_play import connection_proof  # noqa: E402
from mtg_play.contracts import GameSetup, MatchSeat  # noqa: E402
from mtg_play.live_game import run_live_game  # noqa: E402
from mtg_proxy.constants import APP_VERSION  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xmage-root", type=Path, default=connection_proof.DEFAULT_BUNDLE
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "Mtg_Projects/mtg_play_unity/Artifacts"
        / ("PublicArtwork-" + uuid.uuid4().hex[:10]),
    )
    args = parser.parse_args()
    service = CardService()

    def document(rows, deck_id):
        entries = []
        for code, number, count in rows:
            card = service.get_print(set_code=code, collector_number=number)
            if not card:
                raise RuntimeError("PUBLIC_ARTWORK_PRINTING_MISSING")
            entries.append(
                DeckEntry(
                    str(len(entries)),
                    card["name"],
                    count,
                    card_id=card["id"],
                    oracle_id=card["oracle_id"],
                    set_code=code,
                    collector_number=number,
                )
            )
        return DeckDocument(
            deck=Deck(
                deck_id=deck_id,
                name="Public artwork proof",
                format="Custom",
                entries=entries,
            )
        )

    human = document(
        [("ddt", str(i), 9) for i in range(60, 64)] + [("m13", "139", 24)],
        "public-human",
    )
    # A normal native AI deck, with zero-cost creatures so public artwork appears promptly.
    opponent = document([("m21", "274", 40), ("som", "174", 20)], "public-ai")
    setup = GameSetup(
        (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai")), "freeform"
    )
    cancel = threading.Event()
    timer = threading.Timer(300, cancel.set)
    timer.start()
    try:
        result = run_live_game(
            setup,
            {"human": human, "ai": opponent},
            cancel,
            lambda event: print(event["phase"], flush=True),
            version=APP_VERSION,
            xmage_root=args.xmage_root,
            artwork_proof=args.output,
        )
    finally:
        timer.cancel()
    if result.get("cancelled"):
        raise RuntimeError("PUBLIC_ARTWORK_PROOF_TIMEOUT")
    (args.output / "result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
