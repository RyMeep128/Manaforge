"""Embedded local Play foundation, using only Manaforge gameplay contracts."""

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.paths import data_root
from mtg_ui.jobs import JobQueue
from dataclasses import replace
from .lobby import DeckSelection, offline_lobby
from .presentation import SessionController, local_adapter
from .setup import saved_decks
from .table import GameTable
from mtg_editor.card_views import Thumbnails


class PlayWorkspace(W.QWidget):
    def __init__(
        self,
        service,
        home,
        parent=None,
        *,
        adapter_factory=local_adapter,
        deck_provider=None,
        lobby=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Play")
        self.service = service
        self._deck_provider = deck_provider or (
            lambda: saved_decks(data_root(), service)
        )
        self._decks = ()
        self.lobby = lobby or offline_lobby()
        self.lobby.offline_setup()
        self._approved_close = False
        self._view = None
        self._seats = ()
        self._seat_id = self.lobby.local_seat_id
        self.deck_artwork = Thumbnails(service, self)
        self.deck_artwork.updated.connect(self._deck_images)
        self.session = SessionController(
            self,
            adapter_factory=adapter_factory,
            authorized_viewer_id=self.lobby.local_seat_id,
        )
        self.catalog_jobs = JobQueue(self)
        self.catalog_jobs.status.connect(self._catalog_loaded)
        self.catalog_jobs.idle.connect(self._selection_changed)
        self.session.statusChanged.connect(self._status)
        self.session.snapshotChanged.connect(self._show_snapshot)
        self.session.viewCleared.connect(self._clear_view)
        self.session.stopped.connect(self._stopped)
        self.session.jobs.idle.connect(self._selection_changed)
        self.session.interactionPending.connect(self._pending)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        heading = W.QHBoxLayout()
        title = W.QLabel("Play")
        title.setProperty("role", "title")
        heading.addWidget(title)
        heading.addStretch()
        back = W.QPushButton("Home")
        back.clicked.connect(home)
        heading.addWidget(back)
        layout.addLayout(heading)
        intro = W.QLabel("You and your decks against an offline AI opponent.")
        intro.setProperty("role", "subtitle")
        layout.addWidget(intro)
        self.pages = W.QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.setup_page = W.QWidget()
        setup_layout = W.QVBoxLayout(self.setup_page)
        setup_layout.setContentsMargins(0, 16, 0, 0)
        format_row = W.QFormLayout()
        self.format = W.QComboBox()
        self.format.addItem("Freeform", "freeform")
        self.format.addItem("Commander", "commander")
        self.format.setCurrentIndex(self.format.findData(self.lobby.format))
        self.format.currentIndexChanged.connect(self._selection_changed)
        format_row.addRow("Format", self.format)
        setup_layout.addLayout(format_row)
        seats = W.QHBoxLayout()
        self.selectors, self.details, self.covers = [], [], []
        for index, seat in enumerate(self.lobby.seats):
            box = W.QGroupBox(seat.player.name)
            form = W.QFormLayout(box)
            if index == 1:
                opponent_options = W.QHBoxLayout()
                self.use_ai = W.QPushButton("Use AI")
                self.use_ai.setCheckable(True)
                self.use_ai.setChecked(True)
                self.use_ai.setAutoExclusive(True)
                self.invite_friend = W.QPushButton("Invite Friend - Coming Soon")
                self.invite_friend.setEnabled(False)
                self.invite_friend.setToolTip(
                    "Inviting friends will be available with multiplayer."
                )
                opponent_options.addWidget(self.use_ai)
                opponent_options.addWidget(self.invite_friend)
                form.addRow(opponent_options)
            selector = W.QComboBox()
            selector.setMinimumContentsLength(18)
            selector.setSizeAdjustPolicy(
                W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            details = W.QLabel("Choose a saved deck")
            details.setWordWrap(True)
            details.setTextFormat(C.Qt.TextFormat.PlainText)
            form.addRow("Deck", selector)
            form.addRow(details)
            cover = W.QLabel()
            cover.setMinimumHeight(140)
            cover.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
            form.addRow(cover)
            self.selectors.append(selector)
            self.details.append(details)
            self.covers.append(cover)
            selector.currentIndexChanged.connect(self._selection_changed)
            seats.addWidget(box)
        setup_layout.addLayout(seats)
        note = W.QLabel(
            "Offline Play preview. You control your own seat; the AI handles its own decisions."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        setup_layout.addWidget(note)
        setup_layout.addStretch()
        actions = W.QHBoxLayout()
        self.reload = W.QPushButton("Refresh decks")
        self.reload.clicked.connect(self.load_decks)
        actions.addWidget(self.reload)
        actions.addStretch()
        self.start_button = W.QPushButton("Start Game")
        self.start_button.setProperty("buttonRole", "primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_game)
        actions.addWidget(self.start_button)
        setup_layout.addLayout(actions)
        self.pages.addWidget(self.setup_page)
        self.game_page = W.QWidget()
        game_layout = W.QVBoxLayout(self.game_page)
        self.game_heading = W.QLabel("Preparing your table…")
        self.game_heading.setProperty("role", "title")
        self.game_heading.setTextFormat(C.Qt.TextFormat.PlainText)
        game_layout.addWidget(self.game_heading)
        self.table = GameTable(service)
        self.table.command.connect(self._command)
        game_layout.addWidget(self.table, 1)
        game_actions = W.QHBoxLayout()
        game_actions.addStretch()
        self.concede_button = W.QPushButton("Concede")
        self.concede_button.setEnabled(False)
        self.concede_button.clicked.connect(self.concede)
        game_actions.addWidget(self.concede_button)
        self.close_button = W.QPushButton("Close game")
        self.close_button.clicked.connect(self.request_close_game)
        game_actions.addWidget(self.close_button)
        game_layout.addLayout(game_actions)
        self.pages.addWidget(self.game_page)
        self.status = W.QLabel("Loading your decks…")
        self.status.setWordWrap(True)
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        self.status.setAccessibleName("Game status")
        layout.addWidget(self.status)
        self.load_decks()

    def load_decks(self):
        if self.catalog_jobs.busy or self.session.active:
            return
        self.deck_artwork.stopping = False
        self.reload.setEnabled(False)
        self.start_button.setEnabled(False)
        self.status.setText("Loading your saved decks…")
        self.catalog_jobs.submit(lambda cancel, report: self._deck_provider())

    @C.pyqtSlot(str, str, object)
    def _catalog_loaded(self, job, state, value):
        if state not in ("completed", "failed", "cancelled"):
            return
        self.reload.setEnabled(True)
        if state != "completed":
            self.status.setText(
                "Could not load saved decks. Open Deck Editor to review your library, then refresh."
            )
            return
        previous_paths = [
            self._decks[selector.currentData()].path
            if selector.currentData() is not None
            else None
            for selector in self.selectors
        ]
        self._decks, errors = value
        for selector, previous in zip(self.selectors, previous_paths):
            selector.blockSignals(True)
            selector.clear()
            selector.addItem("Choose a saved deck", None)
            for index, deck in enumerate(self._decks):
                selector.addItem(deck.document.deck.name, index)
            for index, deck in enumerate(self._decks):
                if deck.path == previous:
                    selector.setCurrentIndex(index + 1)
            selector.blockSignals(False)
        self.status.setText(
            "Some saved decks could not be read. Review them in Deck Editor."
            if errors
            else "Choose your deck and the AI opponent's deck."
            if self._decks
            else "Save a deck in Deck Editor, then choose Refresh decks."
        )
        self._selection_changed()

    def _selection_changed(self):
        if self.session.active:
            self.start_button.setEnabled(False)
            return
        lobby = replace(self.lobby, format=self.format.currentData())
        for seat, selector in zip(lobby.seats, self.selectors):
            index = selector.currentData()
            selection = None
            if index is not None:
                document = self._decks[index].document
                owner = (
                    seat.deck.owner_id
                    if seat.deck and seat.deck.deck_id == document.deck.deck_id
                    else None
                )
                selection = DeckSelection.local(document, owner_id=owner)
            lobby = lobby.select_deck(seat.seat_id, selection)
        self.lobby = lobby
        for selector, label in zip(self.selectors, self.details):
            index = selector.currentData()
            if index is None:
                label.setText("Choose a saved deck")
            else:
                item = self._decks[index]
                label.setText(
                    item.document.deck.format
                    + (
                        "\nCommander: " + ", ".join(item.commanders)
                        if item.commanders
                        else ""
                    )
                )
                if item.colors is not None:
                    color_names = {
                        "W": "White",
                        "U": "Blue",
                        "B": "Black",
                        "R": "Red",
                        "G": "Green",
                    }
                    label.setText(
                        label.text()
                        + "\nColors: "
                        + (
                            ", ".join(color_names[color] for color in item.colors)
                            or "Colorless"
                        )
                    )
                if self.format.currentData() == "commander" and not item.commanders:
                    label.setText(
                        label.text()
                        + "\nChoose a commander in Deck Editor before starting."
                    )
                elif self.format.currentData() == "freeform" and item.commanders:
                    label.setText(
                        label.text()
                        + "\nThis deck has commanders selected. Choose Commander format."
                    )
        self._deck_images()
        self.start_button.setEnabled(
            not self.session.active
            and not self.session.busy
            and not self.catalog_jobs.busy
            and all(selector.currentData() is not None for selector in self.selectors)
            and all(
                bool(self._decks[selector.currentData()].commanders)
                == (self.format.currentData() == "commander")
                for selector in self.selectors
            )
        )

    def start_game(self):
        if not self.start_button.isEnabled():
            return
        setup = self.lobby.offline_setup()
        decks = self.lobby.selected_documents()

        def oracle_lookup(oracle_id):
            return self.service.database.get_oracle_card(oracle_id)

        self._approved_close = False
        self._seats = setup.seats
        self._seat_id = self.lobby.local_seat_id
        self.table.artwork.stopping = False
        if self.session.start(setup, decks, oracle_lookup=oracle_lookup):
            self.pages.setCurrentWidget(self.game_page)
            self.start_button.setEnabled(False)

    @C.pyqtSlot()
    def _deck_images(self):
        if self.session.active:
            return
        keys = []
        for selector, cover in zip(self.selectors, self.covers):
            index = selector.currentData()
            cover.clear()
            if index is not None:
                cover.setText("No artwork preview")
                key = self._decks[index].cover
                if any(key):
                    keys.append(key)
                    image = self.deck_artwork.get(*key)
                    if image is not None and not image.isNull():
                        cover.setPixmap(
                            image.scaled(
                                110,
                                154,
                                C.Qt.AspectRatioMode.KeepAspectRatio,
                                C.Qt.TransformationMode.SmoothTransformation,
                            )
                        )
        self.deck_artwork.set_visible("setup", keys)

    @C.pyqtSlot(str)
    def _status(self, message):
        self.status.setText(message)
        if not self.session.active and not self.session.closing:
            self.pages.setCurrentWidget(self.setup_page)
            self._selection_changed()

    @C.pyqtSlot()
    def _clear_view(self):
        self._view = None
        self.game_heading.setText("Waiting for your table…")
        self.table.clear()
        self.concede_button.setEnabled(False)

    @C.pyqtSlot()
    def _pending(self):
        self._view = None
        self.table.pending()
        self.concede_button.setEnabled(False)

    @C.pyqtSlot(object)
    def _show_snapshot(self, view):
        if view.viewer_id != self.lobby.local_seat_id:
            return
        self._view = view
        self.game_heading.setText(view.result or "You versus Opponent")
        self.table.present(view)
        self.concede_button.setEnabled(
            not view.result and not self.session.concession_pending
        )

    @C.pyqtSlot(object, str, object)
    def _command(self, view, method, args):
        self.session.submit(view, method, *args)

    def concede(self):
        view = self._view
        if view is None:
            return
        answer = W.QMessageBox.question(
            self,
            "Concede game?",
            "Concede this game to the AI opponent?",
            W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
            W.QMessageBox.StandardButton.No,
        )
        if answer == W.QMessageBox.StandardButton.Yes:
            self.session.concede(view)

    def request_close_game(self):
        if self.session.closing:
            return
        if not self._confirm_close():
            return
        self.session.stop()

    def _confirm_close(self):
        if self._approved_close:
            return True
        answer = W.QMessageBox.question(
            self,
            "Close local game?",
            "End this local session? Your saved decks will remain available.",
            W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
            W.QMessageBox.StandardButton.No,
        )
        self._approved_close = answer == W.QMessageBox.StandardButton.Yes
        return self._approved_close

    @C.pyqtSlot()
    def _stopped(self):
        self.pages.setCurrentWidget(self.setup_page)
        self._selection_changed()

    def prepare_to_close(self):
        if self.session.active or self.session.closing:
            if not self.session.closing and self._confirm_close():
                self.session.stop()
            return False
        self.deck_artwork.stopping = True
        self.deck_artwork.pending.clear()
        self.deck_artwork.next_timer.stop()
        return (
            not self.session.busy
            and not self.catalog_jobs.busy
            and self.table.artwork.shutdown()
            and self.deck_artwork.worker is None
        )

    @property
    def busy(self):
        return (
            self.session.busy
            or self.catalog_jobs.busy
            or self.table.artwork.worker is not None
            or self.deck_artwork.worker is not None
        )
