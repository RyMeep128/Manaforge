"""Card inspection and printing selection, with background catalog/image reads."""
from copy import deepcopy
from pathlib import Path
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from .organization import card_facts
from mtg_core.diagnostics import get_logger


class Result(C.QObject):
    ready = C.pyqtSignal(int, object, str)


class Load(C.QRunnable):
    def __init__(self, token, work, callback, *, context=None):
        super().__init__()
        self.token, self.work = token, work
        self.context = context or {}
        self.operation = getattr(work, '__qualname__', type(work).__name__)
        self.signals = Result()
        self.signals.ready.connect(callback)

    def run(self):
        try:
            self.signals.ready.emit(self.token, self.work(), '')
        except Exception as exc:
            get_logger(__name__).exception('Card details failed operation=%s context=%s request=%s',
                                           self.operation, self.context, self.token)
            self.signals.ready.emit(self.token, None, str(exc))


def apply_printing(document, entry_id, payload):
    entry = next((e for e in document.deck.entries if e.entry_id == entry_id), None)
    if entry is None:
        return
    if entry.card_id == payload.get('id'):
        return
    if entry.oracle_id and payload.get('oracle_id') != entry.oracle_id:
        raise ValueError('The printing must belong to the same card.')
    entry.card_id = payload['id']
    entry.oracle_id = payload.get('oracle_id')
    entry.set_code = payload.get('set')
    entry.collector_number = payload.get('collector_number')
    entry.image_asset_id = None
    for key in ('imported_artwork', 'backside_name', 'backside_short_edge'):
        entry.extras.pop(key, None)
    entry.art_override = None
    entry.pre_cropped = True
    entry.backside_asset_id = None
    entry.backside_pre_cropped = None
    entry.extras['facts'] = card_facts(payload)


def apply_quantity(document, entry_id, quantity):
    entry = next((e for e in document.deck.entries if e.entry_id == entry_id), None)
    if entry is None:
        return
    entry.quantity = max(0, int(quantity))
    if entry.quantity == 0:
        document.deck.entries = [e for e in document.deck.entries if e.entry_id != entry_id]
        document.deck.commander_entry_ids = [key for key in document.deck.commander_entry_ids if key != entry_id]


class CardDetails(W.QDialog):
    printingChosen = C.pyqtSignal(str, object)
    quantityChosen = C.pyqtSignal(str, int)

    def __init__(self, service, entry, parent=None):
        super().__init__(parent)
        self.service, self.entry = service, deepcopy(entry)
        self.token = 0
        self.face = 0
        self.payload = {**(entry.extras.get('facts') or {}), 'name': entry.name,
                        'id': entry.card_id, 'oracle_id': entry.oracle_id}
        self.cache = {}
        self.image_keys = {}
        self.catalog_notice = ''
        self.setWindowTitle(entry.name)
        self.resize(760, 620)
        layout = W.QHBoxLayout(self)
        art = W.QVBoxLayout()
        self.image = W.QLabel('Loading image…')
        self.image.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(300, 420)
        art.addWidget(self.image, 1)
        self.flip = W.QPushButton('↻ Flip card')
        self.flip.setVisible(False)
        self.flip.clicked.connect(self.flip_face)
        art.addWidget(self.flip)
        layout.addLayout(art, 1)
        info = W.QVBoxLayout()
        self.text = W.QTextBrowser()
        facts = entry.extras.get('facts') or {}
        self.text.setPlainText('\n\n'.join(filter(None, [entry.name, facts.get('type_line'),
                               facts.get('oracle_text') or 'Oracle text unavailable in the local catalog.'])))
        info.addWidget(self.text, 1)
        quantity_row = W.QHBoxLayout()
        quantity_row.addWidget(W.QLabel('Quantity in deck'))
        self.quantity = W.QSpinBox()
        self.quantity.setRange(0, 2147483647)
        self.quantity.setValue(entry.quantity)
        self.quantity.setKeyboardTracking(False)
        quantity_row.addWidget(self.quantity)
        self.apply_quantity_button = W.QPushButton('Apply quantity')
        self.apply_quantity_button.setAutoDefault(False)
        self.apply_quantity_button.clicked.connect(self.choose_quantity)
        quantity_row.addWidget(self.apply_quantity_button)
        info.addLayout(quantity_row)
        self.rulings = W.QPushButton('View Oracle text and rulings…')
        self.rulings.setEnabled(bool(entry.oracle_id or entry.card_id))
        self.rulings.clicked.connect(self.show_rulings)
        info.addWidget(self.rulings)
        info.addWidget(W.QLabel('Scryfall printing'))
        self.printings = W.QComboBox()
        self.printings.setMinimumContentsLength(25)
        self.printings.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.printings.setEnabled(False)
        self.printings.currentIndexChanged.connect(self.preview_printing)
        info.addWidget(self.printings)
        self.load_more = W.QPushButton('Load more printings from Scryfall')
        self.load_more.clicked.connect(lambda: self.load_catalog(remote=True))
        info.addWidget(self.load_more)
        self.use = W.QPushButton('Use this printing')
        self.use.setEnabled(False)
        self.use.clicked.connect(self.choose)
        info.addWidget(self.use)
        self.status = W.QLabel('')
        self.status.setWordWrap(True)
        info.addWidget(self.status)
        close = W.QPushButton('Close')
        close.clicked.connect(self.close)
        info.addWidget(close)
        layout.addLayout(info, 1)
        self.load_catalog()

    def submit(self, work, callback):
        self.token += 1
        C.QThreadPool.globalInstance().start(Load(self.token, work, callback, context={
            'entry_id': self.entry.entry_id, 'card_id': self.entry.card_id, 'oracle_id': self.entry.oracle_id}))

    def load_catalog(self, *, remote=False):
        if remote:
            self.status.setText('Loading additional printings from Scryfall…')
        def work():
            payload = self.service.get_card(card_id=self.entry.card_id) if self.entry.card_id else None
            if not payload:
                payload = self.service.get_card(exact_name=self.entry.name)
            if remote and not payload and hasattr(self.service, 'fetch_missing_card'):
                payload = self.service.fetch_missing_card(card_id=self.entry.card_id) if self.entry.card_id else self.service.fetch_missing_card(exact_name=self.entry.name)
            payload = payload or dict(self.entry.extras.get('facts', {}), name=self.entry.name)
            oracle = payload.get('oracle_id') or self.entry.oracle_id
            notice = ''
            try:
                prints = self.service.get_prints(oracle, allow_remote=True) if oracle and remote else (
                    self.service.get_prints(oracle) if oracle else [])
            except (OSError, ValueError) as exc:
                prints = self.service.get_prints(oracle) if oracle else []
                notice = 'Could not load other Scryfall printings; showing cached choices. ' + str(exc)
            return payload, prints, notice
        self.submit(work, self.catalog_loaded)

    def catalog_loaded(self, token, result, error):
        if token != self.token:
            return
        if error:
            self.text.setPlainText(self.entry.name + '\n\n' + (self.entry.extras.get('facts', {}).get('oracle_text') or 'Oracle text unavailable.'))
            self.status.setText('Could not load card details: ' + error)
            return
        payload, prints, self.catalog_notice = result
        rows = [payload] + [p for p in prints if p.get('id') != payload.get('id')]
        self.printings.blockSignals(True)
        self.printings.clear()
        for p in rows:
            label = f"{p.get('set_name') or p.get('set') or 'Unknown set'} · #{p.get('collector_number', '?')} · {p.get('lang', 'en')}"
            self.printings.addItem(label, p)
        self.printings.blockSignals(False)
        self.printings.setEnabled(len(rows) > 1)
        self.preview_printing()

    def preview_printing(self, *_):
        self.payload = self.printings.currentData() or {}
        self.rulings.setEnabled(bool(self.payload.get('oracle_id') or self.entry.oracle_id
                                    or self.payload.get('id') or self.entry.card_id))
        self.face = 0
        self.use.setEnabled(bool(self.payload.get('id')) and self.payload.get('id') != self.entry.card_id)
        self.render_face()

    def show_rulings(self):
        from mtg_ui.rulings import RulingsDialog
        RulingsDialog(self.service, name=self.entry.name,
                      oracle_id=self.payload.get('oracle_id') or self.entry.oracle_id,
                      card_id=self.payload.get('id') or self.entry.card_id, parent=self).exec()

    def flip_face(self):
        self.face = 1 - self.face
        self.render_face()

    def render_face(self):
        faces = self.payload.get('card_faces') or []
        dfc = len(faces) == 2 and all(f.get('image_uris') for f in faces)
        self.flip.setVisible(dfc)
        self.flip.setText('↻ Show front' if self.face else '↻ Show back')
        shown = [faces[self.face]] if dfc else faces or [self.payload]
        paragraphs = []
        for face in shown:
            lines = [face.get('name', self.entry.name), face.get('mana_cost'), face.get('type_line'),
                     face.get('oracle_text') or 'Oracle text unavailable.']
            if 'power' in face:
                lines.append(f"{face['power']}/{face.get('toughness', '?')}")
            if 'loyalty' in face:
                lines.append('Loyalty: ' + str(face['loyalty']))
            paragraphs.append('\n\n'.join(str(line) for line in lines if line))
        self.text.setPlainText('\n\n────\n\n'.join(paragraphs))
        self.image.clear()
        self.image.setText('Loading image…')
        self.status.setText(self.catalog_notice)
        payload, face_index = self.payload, self.face
        current = payload.get('id') == self.entry.card_id
        asset = (self.entry.backside_asset_id if face_index else self.entry.image_asset_id) if current else None
        key = (payload.get('id'), face_index, asset)
        if key in self.cache:
            self.token += 1
            self.show_image(self.token, self.cache[key], '')
            return
        def work():
            if asset:
                data = self.service.get_image_bytes(asset)
            elif face_index:
                urls = faces[face_index].get('image_uris', {})
                url = urls.get('normal') or urls.get('large') or urls.get('png')
                data = self.service.fetch_bytes_fn(url) if url else None
            else:
                path = self.service.ensure_image(payload.get('id'), allow_remote=True) if payload.get('id') else None
                data = Path(path).read_bytes() if path else None
            image = G.QImage.fromData(data or b'')
            return image
        self.image_keys[self.token + 1] = key
        self.submit(work, self.image_loaded)

    def image_loaded(self, token, result, error):
        key = self.image_keys.pop(token, None)
        if key is not None and result is not None:
            self.cache[key] = result
        self.show_image(token, result, error)

    def show_image(self, token, image, error):
        if token != self.token:
            return
        if image is None or image.isNull():
            self.image.setText('Image unavailable')
            if error:
                self.status.setText('Could not load image: ' + error)
            return
        self.image.setPixmap(G.QPixmap.fromImage(image).scaled(340, 476,
            C.Qt.AspectRatioMode.KeepAspectRatio, C.Qt.TransformationMode.SmoothTransformation))

    def choose(self):
        if self.payload.get('id'):
            self.printingChosen.emit(self.entry.entry_id, self.payload)
            self.close()

    def choose_quantity(self):
        quantity = self.quantity.value()
        self.quantityChosen.emit(self.entry.entry_id, quantity)
        self.entry.quantity = quantity
        self.status.setText('Deck quantity updated. Undo is available.')
        if quantity == 0:
            self.close()

    def closeEvent(self, event):
        self.token += 1
        super().closeEvent(event)
