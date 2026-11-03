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


def public_commander_deck(ai, variant="single", scenario="single"):
    rows = (
        [("Forest", "TRK", "325", 99), ("Progenitus", "CON", "121", 1)]
        if ai
        else [
            ("Swamp", "TRK", "321", 99),
            ("Yargle, Glutton of Urborg", "DOM", "113", 1),
        ]
    )
    if not ai and variant == "partners":
        rows = [
            ("Mountain", "TRK", "323", 98),
            ("Rograkh, Son of Rohgahh", "CMR", "197", 1),
            ("Kediss, Emberclaw Familiar", "CMR", "188", 1),
        ]
    if not ai and variant == "background":
        rows = [
            ("Forest", "TRK", "325", 98),
            ("Wilson, Refined Grizzly", "CLB", "261", 1),
            ("Raised by Giants", "CLB", "250", 1),
        ]
    if ai and variant == "partners":
        rows = [
            ("Forest", "TRK", "325", 98),
            ("Thrasios, Triton Hero", "FCA", "58", 1),
            ("Kydele, Chosen of Kruphix", "CMR", "524", 1),
        ]
    if ai and variant == "background":
        rows = [
            ("Swamp", "TRK", "321", 98),
            ("Wilson, Refined Grizzly", "CLB", "261", 1),
            ("Agent of the Iron Throne", "CLB", "107", 1),
        ]
    if not ai and scenario != "single":
        spell = (
            ("Baleful Mastery", "STX", "64", 1)
            if scenario.startswith("exile-")
            else ("Phyrexian Reclamation", "ULG", "63", 1)
            if scenario.startswith("hand-")
            else ("Forever Young", "ELD", "89", 1)
            if scenario.startswith("library-")
            else None
        )
        rows = [
            ("Swamp", "TRK", "321", 98 if spell else 99),
            ("Sidisi, Undead Vizier", "DTK", "120", 1),
        ] + ([spell] if spell else [])
    commanders = {
        "Progenitus",
        "Yargle, Glutton of Urborg",
        "Rograkh, Son of Rohgahh",
        "Kediss, Emberclaw Familiar",
        "Wilson, Refined Grizzly",
        "Raised by Giants",
        "Sidisi, Undead Vizier",
        "Agent of the Iron Throne",
        "Thrasios, Triton Hero",
        "Kydele, Chosen of Kruphix",
    }
    entries = [
        DeckEntry(
            "land"
            if i == 0
            else ("commander-" if name in commanders else "spell-") + str(i),
            name,
            count,
            section="commander" if name in commanders else "mainboard",
            card_id="public-" + code + "-" + number,
            oracle_id="public-oracle-" + str(i),
            set_code=code,
            collector_number=number,
        )
        for i, (name, code, number, count) in enumerate(rows)
    ]
    return DeckDocument(
        deck=Deck(
            deck_id="public-ai" if ai else "public-human",
            name="Public Commander acceptance",
            format="Commander",
            entries=entries,
            commander_entry_ids=[
                entry.entry_id for entry in entries if entry.section == "commander"
            ],
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-decks", action="store_true")
    parser.add_argument(
        "--ai-commander-setup",
        choices=("single", "partners", "background"),
        default="single",
    )
    parser.add_argument("--no-capture", action="store_true")
    parser.add_argument(
        "--commander-scenario",
        choices=(
            "single",
            "tax",
            "grave-decline",
            "hand-accept",
            "hand-decline",
            "exile-accept",
            "exile-decline",
            "library-accept",
            "library-decline",
        ),
        default="single",
    )
    parser.add_argument(
        "--presentation", choices=("current", "table"), default="current"
    )
    parser.add_argument(
        "--commander-setup",
        choices=("single", "partners", "background"),
        default="single",
    )
    parser.add_argument(
        "--format", choices=("freeform", "commander"), default="freeform"
    )
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
    parser.add_argument("--xmage-root", type=Path, help="Explicit pinned engine candidate bundle")
    parser.add_argument("--startup-only", action="store_true", help="Check normal authenticated startup, then cancel without submitting gameplay choices")
    parser.add_argument("--startup-seconds", type=int, default=10, help="Startup-only idle observation duration (1–120 seconds)")
    args = parser.parse_args()
    if not 1 <= args.startup_seconds <= 120:
        parser.error("--startup-seconds must be between 1 and 120")
    if (
        args.public_decks == bool(args.human_deck or args.ai_deck)
        or not args.public_decks
        and not (args.human_deck and args.ai_deck)
    ):
        parser.error("Choose --public-decks or both saved-deck paths")
    args.output.mkdir(parents=True, exist_ok=False)
    documents = {
        "local-player": (
            public_commander_deck(False, args.commander_setup, args.commander_scenario)
            if args.format == "commander"
            else public_deck(False)
        )
        if args.public_decks
        else DeckStore().load(args.human_deck),
        "native-ai": (
            public_commander_deck(True, args.ai_commander_setup)
            if args.format == "commander"
            else public_deck(True)
        )
        if args.public_decks
        else DeckStore().load(args.ai_deck),
    }
    setup = GameSetup(
        (MatchSeat("local-player", "Human"), MatchSeat("native-ai", "AI", "engine_ai")),
        args.format,
    )
    if args.public_decks:
        for seat, document in tuple(documents.items()):
            path = args.output / (seat + ".json")
            DeckStore().save(path, document)
            documents[seat] = DeckStore().load(path)
    launch = LiveGameLaunch()
    cancel = threading.Event()
    startup_timer = None
    started = False

    def progress(value):
        nonlocal startup_timer, started
        print(value["phase"], flush=True)
        if args.startup_only and value["phase"] == "Unity game running":
            started = True
            startup_timer = threading.Timer(args.startup_seconds, cancel.set)
            startup_timer.start()

    try:
        result = run_live_game(
            setup,
            documents,
            cancel,
            progress,
            version=APP_VERSION,
            launch=launch,
            payment_mode=args.payment_mode,
            acceptance=not args.startup_only,
            commander_scenario=args.commander_scenario,
            no_capture=args.no_capture,
            presentation=args.presentation,
            **({"xmage_root": args.xmage_root} if args.xmage_root else {}),
        )
        if args.startup_only:
            if not started or result.get("cancelled") is not True:
                raise RuntimeError("UNITY_GAME_STARTUP_NOT_PROVEN")
            result.update(authenticated_startup=True, gameplay_choices_submitted=False, full_match_verified=False)
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
                    client_errors=launch.client_errors,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print("UNITY_GAME_ACCEPTANCE_FAILED: " + str(error), file=sys.stderr)
        return 1
    finally:
        if startup_timer is not None:
            startup_timer.cancel()
    if args.startup_only:
        print("Normal authenticated startup verified; cancelled without gameplay choices. Full-match acceptance remains pending.")
        print(args.output)
        return 0
    print(
        "Native Commander scenario completed with confirmed inputs and cleanup."
        if args.commander_scenario not in ("single", "tax")
        else "Shuffled saved-deck match completed with native result, confirmed viewer inputs and cleanup."
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
