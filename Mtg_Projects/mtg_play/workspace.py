"""Embedded local Play foundation, using only Manaforge gameplay contracts."""

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.paths import data_root
from mtg_ui.jobs import JobQueue
from dataclasses import replace
from .lobby import DeckSelection, offline_lobby
from .navigation import ModeSelection, PlayLanding, PlayPages
from .presentation import SessionController, local_adapter
from .setup import prepare_catalog, saved_decks
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
        browse_library=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Play")
        self.service = service
        self._deck_provider = deck_provider or (lambda: saved_decks(data_root()))
        self._decks = ()
        self._browse_library = browse_library
        self.lobby = lobby or offline_lobby()
        self.lobby.offline_setup()
        self._approved_close = False
        self._format_confirmed = False
        self._confirmed_format = None
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
        self.catalog_jobs.progress.connect(self._catalog_progress)
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
        self.home_button = W.QPushButton("Home")
        self.home_button.clicked.connect(home)
        heading.addWidget(self.home_button)
        layout.addLayout(heading)
        intro = W.QLabel("You and your decks against an offline AI opponent.")
        intro.setProperty("role", "subtitle")
        layout.addWidget(intro)
        self.pages = PlayPages()
        layout.addWidget(self.pages, 1)
        self.landing_page = PlayLanding()
        self.mode_page = ModeSelection()
        self.pages.addWidget(self.landing_page)
        self.pages.addWidget(self.mode_page)
        self._format_origin = self.landing_page
        self.landing_page.playRequested.connect(lambda: self._show_page(self.mode_page))
        self.landing_page.offlineRequested.connect(self._open_offline)
        self.mode_page.offlineRequested.connect(self._open_offline)
        self.mode_page.backRequested.connect(lambda: self._show_page(self.landing_page))
        self.format_page = W.QWidget()
        format_layout = W.QVBoxLayout(self.format_page)
        format_layout.setContentsMargins(0, 24, 0, 24)
        format_layout.setSpacing(20)
        format_title = W.QLabel("Choose your format")
        format_title.setProperty("role", "title")
        format_layout.addWidget(format_title)
        format_note = W.QLabel(
            "Choose a format before selecting your deck and the AI opponent's deck."
        )
        format_note.setWordWrap(True)
        format_layout.addWidget(format_note)
        format_row = W.QFormLayout()
        self.format = W.QComboBox()
        self.format.addItem("Choose a format", None)
        self.format.addItem("Freeform", "freeform")
        self.format.addItem("Commander", "commander")
        self.format.setAccessibleName("Offline match format")
        format_row.addRow("Format", self.format)
        format_layout.addLayout(format_row)
        format_layout.addStretch()
        format_actions = W.QHBoxLayout()
        self.format_back = W.QPushButton("Back")
        self.format_back.clicked.connect(self._back_from_format)
        format_actions.addWidget(self.format_back)
        format_actions.addStretch()
        self.format_continue = W.QPushButton("Continue to Lobby")
        self.format_continue.setProperty("buttonRole", "primary")
        self.format_continue.setEnabled(False)
        self.format_continue.clicked.connect(self._enter_lobby)
        format_actions.addWidget(self.format_continue)
        format_layout.addLayout(format_actions)
        self.pages.addWidget(self.format_page)
        self.setup_page = W.QScrollArea()
        self.setup_page.setFrameShape(W.QFrame.Shape.NoFrame)
        self.setup_page.setWidgetResizable(True)
        setup_content = W.QWidget()
        self.setup_page.setWidget(setup_content)
        setup_layout = W.QVBoxLayout(setup_content)
        setup_layout.setContentsMargins(0, 16, 0, 0)
        lobby_heading = W.QHBoxLayout()
        self.setup_format = W.QLabel("Offline match lobby")
        self.setup_format.setProperty("role", "title")
        lobby_heading.addWidget(self.setup_format)
        lobby_heading.addStretch()
        self.change_format = W.QPushButton("Change format")
        self.change_format.clicked.connect(self._open_offline)
        lobby_heading.addWidget(self.change_format)
        setup_layout.addLayout(lobby_heading)
        seats = W.QHBoxLayout()
        self.selectors, self.details, self.covers = [], [], []
        self.readiness_labels, self.partner_covers = [], []
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
            readiness = W.QLabel("Choose a deck to check readiness.")
            readiness.setWordWrap(True)
            readiness.setTextFormat(C.Qt.TextFormat.PlainText)
            readiness.setAccessibleName(seat.player.name + " deck readiness")
            form.addRow(readiness)
            self.readiness_labels.append(readiness)
            cover = W.QLabel()
            cover.setMinimumHeight(140)
            cover.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
            partner = W.QLabel()
            partner.setMinimumHeight(140)
            partner.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
            partner.hide()
            cover_row = W.QHBoxLayout()
            cover_row.addWidget(cover)
            cover_row.addWidget(partner)
            form.addRow(cover_row)
            self.partner_covers.append(partner)
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
        engine_note = W.QLabel(
            "XMage validates the selected cards and printings when you start."
        )
        engine_note.setWordWrap(True)
        engine_note.setProperty("role", "muted")
        setup_layout.addWidget(engine_note)
        self.shared_decks = W.QPushButton("Browse shared decks")
        self.shared_decks.setEnabled(callable(self._browse_library))
        self.shared_decks.setToolTip(
            "Use Browse Online to follow a shared deck, then return here and refresh. Accepted cached decks can be used offline."
        )
        self.shared_decks.clicked.connect(self._browse_shared)
        setup_layout.addWidget(self.shared_decks, 0, C.Qt.AlignmentFlag.AlignLeft)
        shared_hint = W.QLabel(
            "Follow a deck in Browse Online, then return here and Refresh decks. Accepted cached copies remain available offline."
        )
        shared_hint.setWordWrap(True)
        shared_hint.setProperty("role", "muted")
        setup_layout.addWidget(shared_hint)
        setup_layout.addStretch()
        actions = W.QHBoxLayout()
        self.lobby_back = W.QPushButton("Back to Play")
        self.lobby_back.clicked.connect(lambda: self._show_page(self.landing_page))
        actions.addWidget(self.lobby_back)
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
        self.format.currentIndexChanged.connect(self._format_changed)
        self._format_changed()
        self.load_decks()

    def _show_page(self, page):
        if self.session.active or self.session.closing:
            return
        self.pages.setCurrentWidget(page)
        self._selection_changed()

    def _open_offline(self):
        if self.session.active or self.session.closing:
            return
        self._format_origin = self.pages.currentWidget()
        self._format_confirmed = False
        self._show_page(self.format_page)

    def _format_changed(self):
        self._format_confirmed = False
        self.format_continue.setEnabled(
            self.format.currentData() in {"freeform", "commander"}
        )
        self._selection_changed()

    def _enter_lobby(self):
        if (
            self.pages.currentWidget() is not self.format_page
            or not self.format_continue.isEnabled()
        ):
            return
        self._format_confirmed = True
        self._confirmed_format = self.format.currentData()
        self.setup_format.setText(self.format.currentText() + " - Offline lobby")
        self._show_page(self.setup_page)

    def _back_from_format(self):
        if (
            self._format_origin is self.setup_page
            and self._confirmed_format is not None
        ):
            self.format.blockSignals(True)
            self.format.setCurrentIndex(self.format.findData(self._confirmed_format))
            self.format.blockSignals(False)
            self._format_confirmed = True
        self._show_page(self._format_origin)

    def load_decks(self):
        if self.catalog_jobs.busy or self.session.active:
            return
        self.deck_artwork.stopping = False
        self.reload.setEnabled(False)
        self.start_button.setEnabled(False)
        self.status.setText("Loading your saved decks…")

        def prepare(cancel, report):
            rows, errors = self._deck_provider()
            return prepare_catalog(
                rows, self.service, cancel=cancel, report=report
            ), errors

        self.catalog_jobs.submit(prepare)

    def _browse_shared(self):
        if (
            not self.session.active
            and not self.session.closing
            and callable(self._browse_library)
        ):
            self._browse_library()

    @C.pyqtSlot(str, object)
    def _catalog_progress(self, job, value):
        if (
            self.session.active
            or self.session.closing
            or job != self.catalog_jobs.current_id
        ):
            return
        if isinstance(value, dict) and value.get("stage") == "local_deck_checks":
            self.status.setText(
                f"Checking local decks: {value['current']} of {value['total']}"
            )

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
            self._decks[selector.currentData()].key
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
                title = deck.document.deck.name
                if deck.source_id:
                    title += " [" + deck.source_label + "]"
                selector.addItem(title, index)
            for index, deck in enumerate(self._decks):
                if deck.key == previous:
                    selector.setCurrentIndex(index + 1)
            selector.blockSignals(False)
        self.status.setText(
            "Some decks could not be read. Review Deck Editor or Browse Online, then refresh."
            if errors
            else (
                "Choose your deck and the AI opponent's deck."
                if self.pages.currentWidget() is self.setup_page
                else "Your saved decks are ready. Choose how you would like to play."
            )
            if self._decks
            else "Save a deck in Deck Editor, then choose Refresh decks."
        )
        self._selection_changed()

    def _selection_changed(self):
        if self.session.active:
            self.start_button.setEnabled(False)
            return
        chosen_format = self.format.currentData()
        lobby = (
            replace(self.lobby, format=chosen_format)
            if chosen_format in {"freeform", "commander"}
            else self.lobby
        )
        for selector in self.selectors:
            selector.setEnabled(self._format_confirmed)
        for seat, selector in zip(lobby.seats, self.selectors):
            index = selector.currentData()
            selection = None
            if index is not None:
                document = self._decks[index].document
                item = self._decks[index]
                selection = DeckSelection.local(
                    document, owner_id=item.owner_id, source_id=item.key
                )
            lobby = lobby.select_deck(seat.seat_id, selection)
        self.lobby = lobby
        selected_checks = []
        for selector, label, readiness in zip(
            self.selectors, self.details, self.readiness_labels
        ):
            index = selector.currentData()
            if index is None:
                label.setText("Choose a saved deck")
                readiness.setText("Choose a deck to check readiness.")
                selected_checks.append(None)
            else:
                item = self._decks[index]
                check = item.readiness(self.format.currentData())
                selected_checks.append(check)
                readiness.setText(
                    check.summary
                    + ("\n" + "\n".join(check.messages) if check.messages else "")
                    if check
                    else "Choose a format to check this deck."
                )
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
                if item.source_id:
                    label.setText(
                        label.text()
                        + "\n"
                        + item.source_label
                        + "\nIsolated match copy; the shared deck is not edited."
                    )
        self._deck_images()
        self.start_button.setEnabled(
            self._format_confirmed
            and self.pages.currentWidget() is self.setup_page
            and self.format.currentData() in {"freeform", "commander"}
            and not self.session.active
            and not self.session.busy
            and not self.catalog_jobs.busy
            and all(selector.currentData() is not None for selector in self.selectors)
            and all(check is not None and check.can_start for check in selected_checks)
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
        for selector, cover, partner in zip(
            self.selectors, self.covers, self.partner_covers
        ):
            index = selector.currentData()
            cover.clear()
            partner.clear()
            partner.hide()
            if index is None:
                continue
            item = self._decks[index]
            previews = (
                item.commander_art[:2]
                if self.format.currentData() == "commander"
                else ()
            )
            if previews:
                artwork = [(cover, previews[0][1], "Commander: " + previews[0][0])]
                if len(previews) == 2:
                    partner.show()
                    artwork.append(
                        (partner, previews[1][1], "Commander: " + previews[1][0])
                    )
            else:
                artwork = [(cover, item.cover, "Deck artwork")]
            for target, key, description in artwork:
                target.setAccessibleName(description)
                target.setText("No artwork preview")
                if any(key):
                    keys.append(key)
                    image = self.deck_artwork.get(*key)
                    if image is not None and not image.isNull():
                        target.setPixmap(
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
            if self.pages.currentWidget() is self.game_page:
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
