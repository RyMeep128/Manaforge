"""Launch the explicitly authorized, one-time collector; no scheduled refresh."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Mtg_Projects' / 'mtg_core'))

from mtg_core.archidekt_ingest import main

if __name__ == '__main__':
    main()
