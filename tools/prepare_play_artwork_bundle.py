"""Prepare public diagnostic launch assets through the existing offline Core cache."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]


def offline(*args, **kwargs):
    raise RuntimeError("CORE_ARTWORK_NETWORK_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--viewer", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--name", action="append", help="Public diagnostic card name"
    )
    selection.add_argument("--printing-id", action="append")
    args = parser.parse_args()
    allowed = (ROOT / "Mtg_Projects/mtg_play_unity/Artifacts").resolve()
    output = args.output.resolve()
    if output == allowed or not output.is_relative_to(allowed) or output.exists():
        parser.error("Choose a new output directory under Unity Artifacts")
    from mtg_core.services import CardService
    from mtg_play.artwork_bundle import export_artwork_bundle

    service = CardService(
        fetch_json_fn=offline, fetch_bytes_fn=offline, fetch_bulk_fn=offline
    )
    ids = args.printing_id or []
    for name in args.name or []:
        card = service.get_card(exact_name=name)
        if not card:
            parser.error("Public diagnostic card is not in the installed catalog")
        ids.append(card["id"])
    manifest, pin = export_artwork_bundle(
        service, ids, output, session_id=args.session, viewer_id=args.viewer
    )
    print(
        f"Prepared {len(manifest['entries'])} cached printings; {len(manifest['unavailable'])} unavailable"
    )
    print(f"Manifest SHA-256: {pin}")


if __name__ == "__main__":
    main()
