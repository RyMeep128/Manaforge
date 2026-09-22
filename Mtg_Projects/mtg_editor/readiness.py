"""Local asset inspection and a clickable, quantity-weighted readiness snapshot."""
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PyQt6 import QtCore as C, QtWidgets as W

LABELS = {'missing-art': 'Missing artwork', 'low-dpi': 'Low DPI',
          'missing-back': 'Missing required / assigned backs', 'dfc': 'Double-faced cards',
          'oversized': 'Oversized cards', 'excluded': 'Excluded / do not print'}


def inspect_readiness(document, service):
    from .proxy_adapter import enable_proxy_imports, project_payload
    enable_proxy_imports()
    from constants import low_dpi_warning_threshold
    from image import effective_dpi_from_dimensions
    from models import ProjectState
    from card_layouts import has_printed_back, PAIRED_BACK_LAYOUTS

    state = ProjectState.from_dict(project_payload(document))
    groups = {key: set() for key in LABELS}
    counts = {key: 0 for key in LABELS}
    unknown = 0
    dimensions_cache = {}

    def dimensions(asset_id, name=None, card_id=None):
        key = (asset_id, name, card_id)
        if key in dimensions_cache:
            return dimensions_cache[key]
        source = None
        if asset_id:
            data = service.get_image_bytes(asset_id)
            source = BytesIO(data) if data else None
        elif name and state.image_dir and (Path(state.image_dir) / name).is_file():
            source = Path(state.image_dir) / name
        elif card_id:
            source = service.get_image_path(card_id)
        result = None
        if source:
            try:
                with Image.open(source) as img:
                    img.load()  # A valid header alone does not prove the image is printable.
                    result = img.size
            except (OSError, ValueError, UnidentifiedImageError):
                pass
        dimensions_cache[key] = result
        return result

    raw_entries = {e.entry_id: e for e in state.card_entries_store.values()}
    for entry in document.deck.entries:
        raw = raw_entries[entry.entry_id]
        facts = entry.extras.get('facts', {})
        if not facts.get('layout') and entry.card_id and hasattr(service, 'get_card'):
            facts = service.get_card(card_id=entry.card_id) or facts
        unknown += int(not facts.get('layout'))
        dfc = facts.get('layout') in PAIRED_BACK_LAYOUTS or has_printed_back(facts)
        size = dimensions(raw.image_asset_id, raw.front_name, entry.card_id)
        low = bool(size and effective_dpi_from_dimensions(*size, raw.front_name,
                                                        pre_cropped=raw.pre_cropped) < low_dpi_warning_threshold)
        assigned = bool(raw.backside_name or raw.backside_asset_id)
        needs_back = dfc or assigned or state.backside_enabled
        back_size = None
        if needs_back:
            if assigned:
                back_size = dimensions(raw.backside_asset_id, raw.backside_name)
            elif not dfc:
                back_size = dimensions(state.backside_default_asset_id, state.backside_default)
        flags = {'missing-art': size is None, 'low-dpi': low,
                 'missing-back': needs_back and back_size is None, 'dfc': dfc,
                 'oversized': bool(entry.extras.get('oversized')),
                 'excluded': entry.section == 'excluded' or entry.do_not_print}
        for key, active in flags.items():
            if active:
                groups[key].add(entry.entry_id)
                counts[key] += entry.quantity
    return {'groups': groups, 'counts': counts, 'threshold': low_dpi_warning_threshold,
            'unknown': unknown}


class ReadinessDialog(W.QDialog):
    filterRequested = C.pyqtSignal(str, object)

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Print readiness')
        layout = W.QVBoxLayout(self)
        note = W.QLabel(f"Local snapshot across all sections. Low DPI means front artwork below {result['threshold']} DPI "
                       "using the printer's source-image calculation. Missing backs include required DFC backs, "
                       "assigned backs, and default backs when duplex output is enabled. Click a total to filter the deck. "
                       "No artwork is downloaded; this is not a full print-layout preflight.")
        note.setWordWrap(True)
        layout.addWidget(note)
        for key, label in LABELS.items():
            ids = result['groups'][key]
            button = W.QPushButton(f"{label}: {result['counts'][key]} copies / {len(ids)} entries")
            button.clicked.connect(lambda checked=False, k=key, selected=ids: self.choose(k, selected))
            layout.addWidget(button)
        if result['unknown']:
            layout.addWidget(W.QLabel(f"{result['unknown']} entries have unknown layout; DFC detection may be incomplete."))
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(540, 360)

    def choose(self, key, ids):
        self.filterRequested.emit(key, ids)
        self.accept()
