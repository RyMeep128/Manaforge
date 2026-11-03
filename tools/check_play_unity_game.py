"""Opt-in normal saved-deck Unity/XMage 1v1 acceptance. No visual capture."""

import argparse
import json
from pathlib import Path
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
sys.path.insert(0, str(ROOT / "Mtg_Projects/mtg_core"))
from mtg_core.decks import Deck, DeckDocument, DeckEntry, DeckStore  # noqa: E402
from mtg_play.contracts import GameSetup, MatchSeat  # noqa: E402
from mtg_play.live_game import run_live_game, LiveGameLaunch  # noqa: E402
from mtg_proxy.constants import APP_VERSION  # noqa: E402


def public_deck(ai):
    rows = (
        [
            ("Forest", "TRK", "325", 24),
            ("Memnite", "SOM", "174", 24),
            ("Phyrexian Walker", "VIS", "152", 12),
        ]
        if ai
        else [
            ("Forest", "TRK", "325", 24),
            ("Memnite", "SOM", "174", 8),
            ("Scryb Sprites", "5ED", "324", 12),
            ("Centaur Courser", "M20", "168", 8),
            ("Evolution Charm", "PLC", "127", 4),
            ("Walking Ballista", "AER", "181", 4),
        ]
    )
    return DeckDocument(
        deck=Deck(
            deck_id="public-ai" if ai else "public-human",
            name="Public shuffled acceptance",
            format="Custom",
            entries=[
                DeckEntry(
                    "entry-" + str(i),
                    name,
                    quantity,
                    card_id="public-" + set + "-" + number,
                    oracle_id="public-oracle-" + str(i),
                    set_code=set,
                    collector_number=number,
                )
                for i, (name, set, number, quantity) in enumerate(rows)
            ],
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-decks", action="store_true")
    parser.add_argument("--human-deck", type=Path)
    parser.add_argument("--ai-deck", type=Path)
    parser.add_argument(
        "--payment-mode", choices=("auto", "manual", "full-control"), default="auto"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "Mtg_Projects/mtg_play_unity/Artifacts"
        / ("LiveGame-" + uuid.uuid4().hex[:10]),
    )
    args = parser.parse_args()
    if (
        args.public_decks == bool(args.human_deck or args.ai_deck)
        or not args.public_decks
        and not (args.human_deck and args.ai_deck)
    ):
        parser.error("Choose --public-decks or both saved-deck paths")
    args.output.mkdir(parents=True, exist_ok=False)
    documents = {
        "local-player": public_deck(False)
        if args.public_decks
        else DeckStore().load(args.human_deck),
        "native-ai": public_deck(True)
        if args.public_decks
        else DeckStore().load(args.ai_deck),
    }
    setup = GameSetup(
        (MatchSeat("local-player", "Human"), MatchSeat("native-ai", "AI", "engine_ai")),
        "freeform",
    )
    if args.public_decks:
        for seat, document in tuple(documents.items()):
            path = args.output / (seat + ".json")
            DeckStore().save(path, document)
            documents[seat] = DeckStore().load(path)
    launch = LiveGameLaunch()
    try:
        result = run_live_game(
            setup,
            documents,
            threading.Event(),
            lambda value: print(value["phase"], flush=True),
            version=APP_VERSION,
            launch=launch,
            payment_mode=args.payment_mode,
            acceptance=True,
        )
        (args.output / "report.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as error:
        (args.output / "failed.json").write_text(
            json.dumps(
                dict(
                    code=str(error),
                    summary=launch.summary,
                    native_code=launch.last_error,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print("UNITY_GAME_ACCEPTANCE_FAILED: " + str(error), file=sys.stderr)
        return 1
    print(
        "Shuffled saved-deck match completed with native result, confirmed viewer inputs and cleanup."
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
