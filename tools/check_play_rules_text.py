"""Packaged Unity + real XMage 1vAI opening rules-text screenshots, using public decks."""

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

CARDS = (
    ("gtc", "92", "Foundry Street Denizen"),
    ("m13", "138", "Krenko, Mob Boss"),
    ("m13", "139", "Krenko's Command"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", choices=[code + "-" + number for code, number, _ in CARDS])
    parser.add_argument(
        "--xmage-root", type=Path, default=connection_proof.DEFAULT_BUNDLE
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "Mtg_Projects/mtg_play_unity/Artifacts"
        / ("RulesText-" + uuid.uuid4().hex[:10]),
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)

    def offline(*args, **kwargs):
        raise RuntimeError("RULES_PROOF_NETWORK_FORBIDDEN")

    service = CardService(
        fetch_json_fn=offline, fetch_bytes_fn=offline, fetch_bulk_fn=offline
    )
    setup = GameSetup(
        (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai")), "freeform"
    )
    reports = []
    for code, number, name in CARDS:
        if args.card and args.card != code + "-" + number:
            continue
        card = service.get_print(set_code=code, collector_number=number)
        if not card or card["name"] != name:
            raise RuntimeError("RULES_PROOF_LOCAL_PRINTING_MISSING")
        # Sixty identical cards guarantee this printing in the shuffled opening.
        document = DeckDocument(
            deck=Deck(
                deck_id="public-rules-proof",
                name="Public rules proof",
                format="Custom",
                entries=[
                    DeckEntry(
                        "public",
                        name,
                        60,
                        card_id=card["id"],
                        oracle_id=card["oracle_id"],
                        set_code=code.upper(),
                        collector_number=number,
                    )
                ],
            )
        )
        destination = args.output / (code + "-" + number)
        cancel = threading.Event()
        timer = threading.Timer(180, cancel.set)
        timer.start()
        try:
            result = run_live_game(
                setup,
                {"human": document, "ai": document},
                cancel,
                lambda event: print(name + ": " + event["phase"], flush=True),
                version=APP_VERSION,
                xmage_root=args.xmage_root,
                rules_text_proof=destination,
            )
        finally:
            timer.cancel()
        if result.get("cancelled"):
            raise RuntimeError("RULES_PROOF_TIMEOUT")
        proof = json.loads(
            (destination / "rules-text-proof.json").read_text(encoding="utf-8-sig")
        )
        if (
            proof["name"] != name
            or not proof["authenticated"]
            or not proof["visible"]
            or not proof["displayed_rules"].strip()
        ):
            raise RuntimeError("RULES_PROOF_FAILED")
        if (
            proof["displayed_rules"] != proof["engine_rules"]
            and proof["displayed_rules"] != card["oracle_text"]
        ):
            raise RuntimeError("RULES_PROOF_TEXT_MISMATCH")
        if proof["mana_cost"] != card["mana_cost"]:
            raise RuntimeError("RULES_PROOF_MANA_MISSING")
        reports.append(dict(name=name, **result))
    (args.output / "report.json").write_text(
        json.dumps(reports, indent=2), encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
