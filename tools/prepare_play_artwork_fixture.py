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

# Public visual cases, not playable decks or engine scenarios. Compound-image
# layouts stay one entry; separately illustrated DFC faces are exported separately.
LAYOUT_NAMES = (
    "Jace, the Mind Sculptor",
    "The Eldest Reborn",
    "Invasion of Zendikar // Awakened Skyclave",
    "Treasure",
    "Soldier",
    "Chandra, Awakened Inferno Emblem",
    "Delver of Secrets // Insectile Aberration",
    "Valakut Awakening // Valakut Stoneforge",
    "Fire // Ice",
    "Bonecrusher Giant // Stomp",
    "Student of Warfare",
    "Ranger Class",
    "Case of the Crimson Pulse",
    "Dollmaker's Shop // Porcelain Gallery",
    "Phyrexian Fleshgorger",
    "Gemrazer",
    "Bruna, the Fading Light",
    "Brisela, Voice of Nightmares",
    "Dungeon of the Mad Mage",
    "The Aether Flues",
    "Behold My Grandeur",
    "Urza",
)


def offline(*args, **kwargs):
    raise RuntimeError("VISUAL_FIXTURE_NETWORK_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory under Unity Artifacts"
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--name", action="append", help="Public fixture card name; never deck data"
    )
    selection.add_argument(
        "--preset", choices=("standard", "layouts"), default="standard"
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
    for name in args.name or (
        LAYOUT_NAMES if args.preset == "layouts" else DEFAULT_NAMES
    ):
        card = service.get_card(exact_name=name)
        if not card:
            parser.error(
                "A requested public card is not in the installed local catalog"
            )
        faces = card.get("card_faces")
        separate_faces = (
            args.preset == "layouts" and faces and not card.get("image_uris")
        )
        for index in range(len(faces) if separate_faces else 1):
            printings.append((card["id"], index))
    try:
        manifest = export_visual_fixture(
            service,
            printings,
            output,
            max_edge=640 if args.preset == "layouts" else 896,
            assets_per_card=1 if args.preset == "layouts" else 3,
        )
    except VisualFixtureError as error:
        parser.exit(1, f"{error}\n")
    print(
        f"Offline fixture: {len(manifest['cards'])} public cards, {len(manifest['assets'])} raw RGBA assets"
    )
    print(
        f"Asset bytes: {sum(asset['byte_length'] for asset in manifest['assets'])}; no downloads or deck reads"
    )
    unavailable = [
        card["selected_face"]
        for card in manifest["cards"]
        if not any(candidate["cached"] for candidate in card["candidates"])
    ]
    if unavailable:
        print("Explicit missing-art placeholders: " + ", ".join(unavailable))


if __name__ == "__main__":
    main()
