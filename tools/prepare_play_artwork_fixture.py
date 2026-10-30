"""Prepare an offline public-card Unity renderer bundle; no downloads or real deck reads."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]

DEFAULT_NAMES = (
    "Grizzly Bears",
    "Lightning Bolt",
    "Counterspell",
    "Sol Ring",
    "Pacifism",
    "Forest",
    "Doom Blade",
)


def offline(*args, **kwargs):
    raise RuntimeError("VISUAL_FIXTURE_NETWORK_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory under Unity Artifacts"
    )
    parser.add_argument(
        "--name", action="append", help="Public fixture card name; never deck data"
    )
    args = parser.parse_args()
    allowed = (ROOT / "Mtg_Projects/mtg_play_unity/Artifacts").resolve()
    output = args.output.resolve()
    if output == allowed or not output.is_relative_to(allowed):
        parser.error("Fixture output must be a new directory under Unity Artifacts")
    if output.exists():
        parser.error("Fixture output already exists; choose a fresh directory")
    from mtg_core.services import CardService
    from mtg_play.visual_fixture import VisualFixtureError, export_visual_fixture

    service = CardService(
        fetch_json_fn=offline, fetch_bytes_fn=offline, fetch_bulk_fn=offline
    )
    printings = []
    for name in args.name or DEFAULT_NAMES:
        card = service.get_card(exact_name=name)
        if not card:
            parser.error(
                "A requested public card is not in the installed local catalog"
            )
        printings.append((card["id"], 0))
    try:
        manifest = export_visual_fixture(service, printings, output)
    except VisualFixtureError as error:
        parser.exit(1, f"{error}\n")
    print(
        f"Offline fixture: {len(manifest['cards'])} public cards, {len(manifest['assets'])} raw RGBA assets"
    )
    print(
        f"Asset bytes: {sum(asset['byte_length'] for asset in manifest['assets'])}; no downloads or deck reads"
    )


if __name__ == "__main__":
    main()
