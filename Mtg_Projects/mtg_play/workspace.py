"""Embedded local Play foundation, using only Manaforge gameplay contracts."""

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.paths import data_root
from mtg_ui.jobs import JobQueue
from .contracts import GameSetup, MatchSeat
from .presentation import SessionController, local_adapter
from .setup import saved_decks


class PlayWorkspace(W.QWidget):
    def __init__(
        self,
        service,
        home,
        parent=None,
        *,
        adapter_factory=local_adapter,
        deck_provider=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Play")
        self.service = service
        self._deck_provider = deck_provider or (lambda: saved_decks(data_root()))
        self._decks = ()
        self._approved_close = False
        self.session = SessionController(self, adapter_factory=adapter_factory)
        self.catalog_jobs = JobQueue(self)
        self.catalog_jobs.status.connect(self._catalog_loaded)
        self.catalog_jobs.idle.connect(self._selection_changed)
        self.session.statusChanged.connect(self._status)
        self.session.snapshotChanged.connect(self._show_snapshot)
        self.session.viewCleared.connect(self._clear_view)
        self.session.stopped.connect(self._stopped)
        self.session.jobs.idle.connect(self._selection_changed)
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
        intro = W.QLabel("Two players. Your decks. One table.")
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
        format_row.addRow("Format", self.format)
        setup_layout.addLayout(format_row)
        seats = W.QHBoxLayout()
        self.names, self.selectors, self.details = [], [], []
        for index in range(2):
            box = W.QGroupBox(f"Player {index + 1}")
            form = W.QFormLayout(box)
            name = W.QLineEdit(f"Player {index + 1}")
            selector = W.QComboBox()
            selector.setMinimumContentsLength(18)
            selector.setSizeAdjustPolicy(
                W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            details = W.QLabel("Choose a saved deck")
            details.setWordWrap(True)
            details.setTextFormat(C.Qt.TextFormat.PlainText)
            form.addRow("Name", name)
            form.addRow("Deck", selector)
            form.addRow(details)
            self.names.append(name)
            self.selectors.append(selector)
            self.details.append(details)
            selector.currentIndexChanged.connect(self._selection_changed)
            name.textChanged.connect(self._selection_changed)
            seats.addWidget(box)
        setup_layout.addLayout(seats)
        note = W.QLabel(
            "Local Play preview • The game interface is being built in stages. "
            "This foundation connects your decks to the local rules engine; "
            "battlefield interactions arrive in the next milestone."
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
        self.game_summary = W.QLabel()
        self.game_summary.setWordWrap(True)
        self.game_summary.setTextFormat(C.Qt.TextFormat.PlainText)
        game_layout.addWidget(self.game_summary)
        game_layout.addStretch()
        self.close_button = W.QPushButton("Close game")
        self.close_button.clicked.connect(self.request_close_game)
        game_layout.addWidget(self.close_button)
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
            else "Choose a deck for each player."
            if self._decks
            else "Save a deck in Deck Editor, then choose Refresh decks."
        )
        self._selection_changed()

    def _selection_changed(self):
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
        self.start_button.setEnabled(
            not self.session.active
            and not self.catalog_jobs.busy
            and all(selector.currentData() is not None for selector in self.selectors)
            and all(name.text().strip() for name in self.names)
        )

    def start_game(self):
        if not self.start_button.isEnabled():
            return
        from copy import deepcopy

        setup = GameSetup(
            tuple(
                MatchSeat(f"local-{index + 1}", name.text().strip())
                for index, name in enumerate(self.names)
            ),
            self.format.currentData(),
        )
        # Isolate selected documents from edits while starting; retain every field.
        decks = tuple(
            deepcopy(self._decks[selector.currentData()].document)
            for selector in self.selectors
        )

        def oracle_lookup(oracle_id):
            return self.service.database.get_oracle_card(oracle_id)

        self._approved_close = False
        if self.session.start(setup, decks, oracle_lookup=oracle_lookup):
            self.pages.setCurrentWidget(self.game_page)
            self.start_button.setEnabled(False)

    @C.pyqtSlot(str)
    def _status(self, message):
        self.status.setText(message)
        if not self.session.active and not self.session.closing:
            self.pages.setCurrentWidget(self.setup_page)
            self._selection_changed()

    @C.pyqtSlot()
    def _clear_view(self):
        self.game_heading.setText("Waiting for your table…")
        self.game_summary.clear()

    @C.pyqtSlot(object)
    def _show_snapshot(self, view):
        self.game_heading.setText(view.result or "Your local game is connected")
        players = "\n".join(
            f"{player.name} · {player.life} life · {player.hand_count} cards in hand"
            for player in view.players
        )
        flow = " · ".join(str(value) for value in (view.phase, view.step) if value)
        self.game_summary.setText(
            players
            + ("\nTurn " + str(view.turn) if view.turn is not None else "")
            + (" · " + flow if flow else "")
            + "\nBattlefield controls are coming in the next milestone."
        )

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
        return not self.session.busy and not self.catalog_jobs.busy
