"""Paginated local catalog browser. Read jobs never wait behind downloads."""

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W

from mtg_core.catalog_workspace import CatalogWorkspace
from .jobs import JobQueue


class CardBrowser(W.QWidget):
    downloadRequested = C.pyqtSignal(object, object)

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.catalog = CatalogWorkspace(service)
        self.reads = JobQueue(self)
        self.reads.status.connect(self.result)
        self.pending = {}
        self.revision = 0
        self.offset = 0
        self.history = []
        self.rows = []
        self.oracle_ids = None
        self.loaded = set()
        layout = W.QVBoxLayout(self)
        bar = W.QHBoxLayout()
        self.search = W.QLineEdit()
        self.search.setPlaceholderText(
            "Search local cards · name, o:draw, t:creature, c:red, id:wu, mv:3, r:rare, f:commander, cn:123"
        )
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search local card database")
        bar.addWidget(self.search, 1)
        self.mode = W.QComboBox()
        self.mode.addItems(["Unique cards", "All printings"])
        bar.addWidget(self.mode)
        self.view = W.QComboBox()
        self.view.addItems(["Grid", "List"])
        self.view.currentIndexChanged.connect(self.change_view)
        bar.addWidget(self.view)
        layout.addLayout(bar)
        filters = W.QHBoxLayout()
        self.set_filter = W.QLineEdit()
        self.set_filter.setPlaceholderText("Set name or code")
        filters.addWidget(self.set_filter)
        self.missing = W.QCheckBox("Missing artwork")
        filters.addWidget(self.missing)
        self.scope = W.QComboBox()
        self.scope.addItems(
            [
                "Selected printing(s)",
                "Selected card · all local printings",
                "Current set",
                "All filtered results",
            ]
        )
        filters.addWidget(self.scope)
        download = W.QPushButton("Download artwork…")
        download.clicked.connect(self.download)
        filters.addWidget(download)
        layout.addLayout(filters)
        advanced = W.QGroupBox("Card filters")
        form = W.QGridLayout(advanced)
        self.fields = {}
        for index, (label, key) in enumerate(
            (
                ("Color", "c"),
                ("Identity", "id"),
                ("Mana value", "mv"),
                ("Type", "t"),
                ("Rarity", "r"),
                ("Legal in", "f"),
            )
        ):
            field = W.QLineEdit()
            field.setPlaceholderText(
                {
                    "c": "WUBRG",
                    "id": "WUBRG",
                    "mv": "3",
                    "t": "Creature",
                    "r": "rare",
                    "f": "commander",
                }[key]
            )
            form.addWidget(W.QLabel(label), index // 3, (index % 3) * 2)
            form.addWidget(field, index // 3, (index % 3) * 2 + 1)
            self.fields[key] = field
        layout.addWidget(advanced)
        split = W.QSplitter()
        self.cards = W.QListWidget()
        self.cards.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.cards.setResizeMode(W.QListView.ResizeMode.Adjust)
        self.cards.setWordWrap(True)
        self.cards.currentRowChanged.connect(self.select)
        self.cards.verticalScrollBar().valueChanged.connect(self.visible_images)
        split.addWidget(self.cards)
        detail = W.QWidget()
        d = W.QVBoxLayout(detail)
        self.preview = W.QLabel("Select a card")
        self.preview.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        d.addWidget(self.preview)
        self.face = 0
        self.flip = W.QPushButton("Flip face")
        self.flip.clicked.connect(self.flip_face)
        self.flip.hide()
        d.addWidget(self.flip)
        self.details = W.QPlainTextEdit()
        self.details.setReadOnly(True)
        d.addWidget(self.details, 1)
        copy = W.QPushButton("Copy name")
        copy.clicked.connect(self.copy_name)
        d.addWidget(copy)
        prints = W.QPushButton("View local printings")
        prints.clicked.connect(self.printings)
        d.addWidget(prints)
        split.addWidget(detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        bottom = W.QHBoxLayout()
        self.previous = W.QPushButton("Previous")
        self.previous.clicked.connect(self.back)
        self.next = W.QPushButton("Next")
        self.next.clicked.connect(self.forward)
        self.message = W.QLabel("Local installed catalog only")
        bottom.addWidget(self.previous)
        bottom.addWidget(self.message, 1)
        bottom.addWidget(self.next)
        layout.addLayout(bottom)
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.reload)
        for signal in (
            self.search.textChanged,
            self.set_filter.textChanged,
            self.mode.currentIndexChanged,
            self.missing.toggled,
        ):
            signal.connect(self.schedule)
        shortcut = G.QShortcut(G.QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.search.setFocus)
        copy_shortcut = G.QShortcut(G.QKeySequence("Ctrl+C"), self.cards)
        copy_shortcut.setContext(C.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy_shortcut.activated.connect(self.copy_name)
        for field in self.fields.values():
            field.textChanged.connect(self.schedule)
        self.change_view()
        C.QTimer.singleShot(0, self.reload)

    def change_view(self):
        grid = self.view.currentIndex() == 0
        self.cards.setViewMode(
            W.QListView.ViewMode.IconMode if grid else W.QListView.ViewMode.ListMode
        )
        self.cards.setIconSize(C.QSize(120, 168) if grid else C.QSize(36, 50))
        self.cards.setGridSize(C.QSize(155, 225) if grid else C.QSize())
        C.QTimer.singleShot(0, self.visible_images)

    def schedule(self):
        self.revision += 1
        self.reads.cancel_all()
        self.oracle_ids = None
        self.offset = 0
        self.history.clear()
        self.timer.start()

    def query(self):
        terms = [self.search.text()]
        for key, field in self.fields.items():
            value = field.text().strip()
            if value:
                value = value.replace("\\", "\\\\").replace('"', '\\"')
                terms.append(f'{key}:"{value}"')
        return " ".join(terms)

    def options(self):
        return dict(
            unique=self.mode.currentIndex() == 0,
            set_filter=self.set_filter.text().strip(),
            missing=self.missing.isChecked(),
            oracle_ids=self.oracle_ids,
        )

    def reload(self):
        self.revision += 1
        self.reads.cancel_all()
        revision = self.revision
        query, options, offset = self.query(), self.options(), self.offset
        options["oracle_ids"] = self.oracle_ids
        self.message.setText("Searching local catalog…")
        self.next.setEnabled(False)
        self.previous.setEnabled(False)
        job = self.reads.submit(
            lambda cancel, report: self.catalog.page(
                query, offset=offset, cancel=cancel, **options
            ),
            quiet=True,
        )
        self.pending[job] = ("page", revision, None)

    def result(self, job, state, value):
        if state not in ("completed", "failed", "cancelled"):
            return
        kind, revision, target = self.pending.pop(job, ("", -1, None))
        if revision != self.revision:
            return
        if state == "failed":
            self.message.setText(str(value))
            self.previous.setEnabled(bool(self.history))
            return
        if state != "completed":
            return
        if kind == "page":
            self.rows, self.next_offset, more = value
            self.cards.clear()
            self.loaded.clear()
            self.face = 0
            self.flip.hide()
            self.preview.clear()
            self.details.clear()
            for row in self.rows:
                p = row.payload
                item = W.QListWidgetItem(
                    f"{row.name}\n{row.set_code or ''} · {row.collector_number or ''} · {p.get('lang', '')}\n{' · '.join(p.get('frame_effects') or [])}"
                )
                placeholder = G.QPixmap(120, 168)
                placeholder.fill(self.palette().alternateBase().color())
                painter = G.QPainter(placeholder)
                painter.setPen(self.palette().text().color())
                painter.drawText(
                    placeholder.rect(),
                    C.Qt.AlignmentFlag.AlignCenter,
                    "Artwork\nnot cached",
                )
                painter.end()
                item.setIcon(G.QIcon(placeholder))
                item.setToolTip(row.name)
                self.cards.addItem(item)
            self.message.setText(
                f"{len(self.rows)} results · local catalog"
                if self.rows
                else "No matches on this page"
                + (" · Next continues the artwork scan" if more else "")
            )
            self.next.setEnabled(more)
            self.previous.setEnabled(bool(self.history))
            C.QTimer.singleShot(0, self.visible_images)
        elif kind == "face":
            index, face = target
            if self.cards.currentRow() == index and self.face == face:
                if value.isNull():
                    self.preview.setText("Artwork not cached")
                else:
                    self.preview.setPixmap(G.QPixmap.fromImage(value))
        elif kind == "image":
            if not value.isNull() and target < self.cards.count():
                self.cards.item(target).setIcon(G.QIcon(G.QPixmap.fromImage(value)))
                if self.cards.currentRow() == target and self.face == 0:
                    self.preview.setPixmap(G.QPixmap.fromImage(value))

    def visible_images(self):
        for index, row in enumerate(self.rows):
            if index in self.loaded or not self.cards.visualItemRect(
                self.cards.item(index)
            ).intersects(self.cards.viewport().rect()):
                continue
            self.loaded.add(index)
            service = self.catalog.service

            def load(cancel, report, card_id=row.card_id):
                path = service.get_image_path(card_id)
                if not path:
                    return G.QImage()
                reader = G.QImageReader(path)
                size = reader.size()
                size.scale(240, 336, C.Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
                return reader.read()

            job = self.reads.submit(load, quiet=True)
            self.pending[job] = ("image", self.revision, index)

    def select(self, index):
        if not 0 <= index < len(self.rows):
            return
        self.face = 0
        row = self.rows[index]
        p = row.payload
        self.flip.setVisible(len(p.get("card_faces") or []) > 1)
        faces = p.get("card_faces") or [p]
        self.details.setPlainText(
            "\n\n".join(
                "\n".join(
                    str(f.get(k) or "")
                    for k in (
                        "name",
                        "mana_cost",
                        "type_line",
                        "oracle_text",
                        "power",
                        "toughness",
                    )
                )
                for f in faces
            )
            + "\n\n"
            + str(p.get("legalities") or {})
        )
        icon = self.cards.item(index).icon()
        self.preview.setPixmap(icon.pixmap(240, 336))
        if icon.isNull():
            self.preview.setText("Artwork not cached")

    def flip_face(self):
        index = self.cards.currentRow()
        if not 0 <= index < len(self.rows):
            return
        row = self.rows[index]
        self.face = (self.face + 1) % len(
            row.payload.get("card_faces") or [row.payload]
        )
        face = self.face
        self.preview.setText("Loading face…")

        def read(cancel, report):
            from mtg_core.catalog_workspace import artwork_faces

            variant = (
                f"face-{face}"
                if face and face in artwork_faces(row.payload)
                else "default"
            )
            path = self.catalog.service.get_image_path(row.card_id, variant)
            if not path:
                return G.QImage()
            reader = G.QImageReader(path)
            size = reader.size()
            size.scale(240, 336, C.Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(size)
            image = reader.read()
            return (
                image.transformed(G.QTransform().rotate(180))
                if face and row.payload.get("layout") == "flip"
                else image
            )

        job = self.reads.submit(read, quiet=True)
        self.pending[job] = ("face", self.revision, (index, face))

    def copy_name(self):
        index = self.cards.currentRow()
        if 0 <= index < len(self.rows):
            W.QApplication.clipboard().setText(self.rows[index].name)

    def printings(self):
        index = self.cards.currentRow()
        if index < 0:
            return
        oracle_id = self.rows[index].oracle_id
        self.search.clear()
        self.set_filter.clear()
        self.missing.setChecked(False)
        for field in self.fields.values():
            field.clear()
        self.mode.setCurrentIndex(1)
        self.oracle_ids = [oracle_id]
        self.timer.stop()
        self.reload()

    def forward(self):
        self.history.append(self.offset)
        self.offset = self.next_offset
        self.reload()

    def back(self):
        if self.history:
            self.offset = self.history.pop()
            self.reload()

    def download(self):
        selected = [self.rows[self.cards.row(i)] for i in self.cards.selectedItems()]
        scope = self.scope.currentIndex()
        if scope < 2 and not selected:
            self.message.setText("Select a card or printing first.")
            return
        query, options = self.query(), self.options()
        if scope == 2 and not options["set_filter"]:
            self.message.setText("Enter a set name or code first.")
            return
        if scope == 0:
            work = lambda cancel, report: self.catalog.download(
                selected, cancel=cancel, report=report
            )
            label = (
                f"{len(selected)} selected printing(s), including image-bearing faces"
            )
        elif scope == 1:
            ids = {row.oracle_id for row in selected}

            def work(cancel, report):
                offset = 0
                while True:
                    rows, offset, more = self.catalog.page(
                        unique=False, oracle_ids=ids, offset=offset, cancel=cancel
                    )
                    self.catalog.download(rows, cancel=cancel, report=report)
                    if not more:
                        break

            label = f"All locally installed printings of {len(ids)} selected card(s)"
        else:
            if scope == 2:
                query = ""
                options.update(unique=False, missing=False, oracle_ids=None)
            work = lambda cancel, report: self.catalog.download_query(
                query, cancel=cancel, report=report, **options
            )
            label = (
                "Every matching local printing in this set"
                if scope == 2
                else "All results matching the current filters across every page"
            )
        self.downloadRequested.emit(label, work)
