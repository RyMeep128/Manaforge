"""Expand the existing EDHREC snapshot with separately stored filtered cohorts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Mtg_Projects" / "mtg_core"))

from mtg_core.edhrec_cohorts import main

if __name__ == "__main__":
    main()
