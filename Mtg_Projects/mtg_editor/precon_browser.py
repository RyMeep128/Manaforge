"""Precon selection reusing the cancellable deck import review dialog."""
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.precons import load_catalog, decklist_entries, prepare_precon, cover_asset
from .decklist_dialogs import ImportDecklist, ImportWorker


class CatalogWorker(C.QThread):
    def __init__(self, service, parent):
        super().__init__(parent)
        self.service, self.records, self.error = service, [], ''

    def run(self):
        try:
            cards = {}
            for record in load_catalog():
                if self.isInterruptionRequested():
                    return
                colors, complete, featured = set(), True, None
                playable = [r for r in record['entries'] if r['section'] in ('commander', 'mainboard')]
                playable.sort(key=lambda r: r['section'] != 'commander')
                for row in playable:
                    if self.isInterruptionRequested():
                        return
                    name = row['name']
                    if name not in cards:
                        cards[name] = self.service.get_card(exact_name=name)
                    card = cards[name]
                    if not card:
                        complete = False
                        continue
                    colors.update(card.get('color_identity', []))
                    if featured is None:
                        featured = card
                record['colors'] = ''.join(c for c in 'WUBRG' if c in colors)
                record['colors_complete'] = complete
                record['featured'] = featured
                record['cover_asset_id'] = cover_asset(record, self.service, offline=True)
                self.records.append(record)
        except Exception as exc:
            self.error = str(exc)


class PreconWorker(ImportWorker):
    def __init__(self, record, service, remote, parent):
        super().__init__('', service, remote, parent)
        self.record = record
        self.cover_asset_id = None

    def run(self):
        try:
            self.result = prepare_precon(self.record, self.service, allow_remote=self.remote,
                progress=self.progress.emit, cancelled=self.cancelled.is_set)
            if self.result is not None and not self.cancelled.is_set():
                from mtg_core.datasets import InstallationState
                self.cover_asset_id = cover_asset(self.record, self.service,
                    offline=InstallationState().get('artwork_mode', 'on_demand') == 'full_offline')
        except Exception as exc:
            self.error = str(exc)


class PreconBrowser(ImportDecklist):
    def __init__(self, service, thumbnails, parent=None):
        super().__init__(service, parent)
        self.setWindowTitle('Create from Precon')
        self.resize(1000, 850)
        self.records, self.record, self.catalog_worker = [], None, None
        self.cover_asset_id = None
        self.thumbnails = thumbnails
        self.input_mode.hide()
        self.file_button.hide()
        self.artwork.hide()
        self.source.setReadOnly(True)
        self.source.setMaximumHeight(150)
        self.layout().itemAt(0).widget().setText(
            'Choose an original preconstructed deck, then review all cards before creating an independent deck. '
            'Printings follow the source: some variants, especially basic lands, are inferred.')
        controls = W.QWidget()
        form = W.QVBoxLayout(controls)
        self.search = W.QLineEdit()
        self.search.setPlaceholderText('Search name, commander, set, product, or release year')
        self.search.setAccessibleName('Search preconstructed decks')
        form.addWidget(self.search)
        filters = W.QHBoxLayout()
        self.format_filter, self.year_filter, self.color_filter = W.QComboBox(), W.QComboBox(), W.QComboBox()
        self.format_filter.addItem('All formats', '')
        self.year_filter.addItem('All release years', '')
        self.color_filter.addItem('All colors', '')
        for label, value in [('White', 'W'), ('Blue', 'U'), ('Black', 'B'), ('Red', 'R'), ('Green', 'G'), ('Colorless', 'C')]:
            self.color_filter.addItem(label, value)
        for widget in (self.format_filter, self.year_filter, self.color_filter):
            filters.addWidget(widget)
            widget.currentIndexChanged.connect(self.filter_records)
        form.addLayout(filters)
        split = W.QHBoxLayout()
        self.decks = W.QListWidget()
        self.decks.setAccessibleName('Official preconstructed deck catalog')
        split.addWidget(self.decks, 1)
        self.cover = W.QLabel('Loading local catalog…')
        self.cover.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.cover.setMinimumSize(160, 200)
        split.addWidget(self.cover)
        form.addLayout(split)
        self.deck_name = W.QLineEdit()
        self.deck_name.setAccessibleName('New deck name')
        form.addWidget(self.deck_name)
        self.layout().insertWidget(1, controls, 2)
        self.search.textChanged.connect(self.filter_records)
        self.decks.currentRowChanged.connect(self.select_record)
        self.resolve_button.setEnabled(False)
        self.apply_button.setText('Create deck from reviewed precon')
        self.thumbnails.updated.connect(self.update_cover)
        self.catalog_worker = CatalogWorker(service, self)
        self.catalog_worker.finished.connect(self.catalog_loaded)
        self.catalog_worker.start()

    def catalog_loaded(self):
        worker, self.catalog_worker = self.catalog_worker, None
        self.records = worker.records
        self.messages.setPlainText(worker.error or f'{len(self.records)} preconstructed products available. '
            'Colors and featured artwork use the local card catalog. Missing card data may limit filters.')
        worker.deleteLater()
        for fmt in sorted({r['format'] for r in self.records}):
            self.format_filter.addItem(fmt, fmt)
        for year in sorted({r['release_date'][:4] for r in self.records}, reverse=True):
            self.year_filter.addItem(year, year)
        self.filter_records()

    def filter_records(self):
        if self.worker is not None:
            return
        query = self.search.text().casefold().split()
        self.decks.clear()
        for record in self.records:
            commanders = ', '.join(e['name'] for e in record['entries'] if e['section'] == 'commander')
            text = ' '.join([record['name'], record['set_name'], record['set_code'],
                             record['product_type'], record['release_date'], commanders]).casefold()
            color = self.color_filter.currentData()
            if (any(term not in text for term in query)
                or self.format_filter.currentData() not in ('', record['format'])
                or self.year_filter.currentData() not in ('', record['release_date'][:4])
                or (color and (not record['colors_complete'] or
                    (bool(record['colors']) if color == 'C' else color not in record['colors'])))):
                continue
            colors = record['colors'] or ('Colorless' if record['colors_complete'] else 'Unknown colors')
            item = W.QListWidgetItem(f"{record['name']} · {record['format']} · {colors}\n"
                f"{record['set_name']} · {record['release_date'][:4]}\n{commanders}")
            item.setData(C.Qt.ItemDataRole.UserRole, record)
            self.decks.addItem(item)
        if self.decks.count():
            self.decks.setCurrentRow(0)

    def select_record(self, index):
        self.invalidate()
        item = self.decks.item(index)
        self.record = item.data(C.Qt.ItemDataRole.UserRole) if item else None
        self.resolve_button.setEnabled(bool(self.record))
        self.deck_name.setText(self.record['name'] if self.record else '')
        self.source.setPlainText('\n'.join(f'{r.count} {r.name} ({r.set_code or ""}) '
            f'{r.collector_number or ""} [{r.section}]' for r in decklist_entries(self.record)) if self.record else '')
        self.update_cover()

    def update_cover(self):
        featured = self.record.get('featured') if self.record else None
        card_id = featured.get('id') if featured else None
        asset = self.record.get('cover_asset_id') if self.record else None
        key = (None, asset) if asset else (card_id, None)
        self.thumbnails.set_visible(id(self), [key] if any(key) else [])
        pixmap = self.thumbnails.get(*key) if any(key) else None
        if pixmap is not None and not pixmap.isNull():
            self.cover.setPixmap(pixmap.scaled(175, 245, C.Qt.AspectRatioMode.KeepAspectRatio,
                                             C.Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover.setText('Featured card artwork\nunavailable locally' if self.record else 'No matching precons')

    def make_worker(self, source, public_url):
        self.decks.setEnabled(False)
        for widget in (self.search, self.format_filter, self.year_filter, self.color_filter):
            widget.setEnabled(False)
        return PreconWorker(self.record, self.service, self.remote.isChecked(), self)

    def resolved(self):
        self.cover_asset_id = self.worker.cover_asset_id
        super().resolved()
        self.decks.setEnabled(True)
        for widget in (self.search, self.format_filter, self.year_filter, self.color_filter):
            widget.setEnabled(True)

    def accept(self):
        if self.worker is not None or self.catalog_worker is not None or not self.result:
            return
        self.thumbnails.set_visible(id(self), [])
        super().accept()

    def closeEvent(self, event):
        if self.catalog_worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if self.catalog_worker is not None:
            self.catalog_worker.requestInterruption()
            self.catalog_worker.finished.connect(self.reject)
            return
        self.thumbnails.set_visible(id(self), [])
        super().reject()
