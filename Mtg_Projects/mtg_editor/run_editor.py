from pathlib import Path
import sys

products = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(products))
sys.path.insert(0, str(products / 'mtg_core'))

from mtg_editor.gui import main

if __name__ == '__main__':
    main()
