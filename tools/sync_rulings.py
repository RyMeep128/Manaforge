"""Download Scryfall rulings for every card in Manaforge's local catalog."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Mtg_Projects' / 'mtg_core'))

from mtg_core.services import CardService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-path', help='Card database (defaults to the shared app catalog)')
    parser.add_argument('--rulings-path', help='Override the offline rulings database location')
    args = parser.parse_args()
    print('Downloading bulk rulings from Scryfall; existing cache is preserved on failure.', flush=True)
    try:
        result = CardService(db_path=args.db_path, rulings_path=args.rulings_path).sync_all_rulings()
    except Exception as exc:
        print(f'Rulings update failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
