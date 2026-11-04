"""Saved-deck launcher for Unity gameplay; game decisions belong to Unity/Java."""

from copy import deepcopy
from dataclasses import replace
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.paths import data_root
from mtg_ui.jobs import JobQueue
from .live_game import run_live_game, LiveGameLaunch
from .lobby import DeckSelection, offline_lobby
from .setup import saved_decks, prepare_catalog


class PlayWorkspace(W.QWidget):
    def __init__(self, service, home, parent=None, *, deck_provider=None,
                 lobby=None, browse_library=None):
        super().__init__(parent)
        self.setWindowTitle("Play")
        self.service = service
        self.lobby = lobby or offline_lobby()
        self._deck_provider = deck_provider or (lambda: saved_decks(data_root()))
        self._decks = ()
        self._native_launch = None
        self.native_jobs = JobQueue(self)
        self.native_jobs.progress.connect(self._native_progress)
        self.native_jobs.status.connect(self._native_status)
        self.native_jobs.idle.connect(self._selection_changed)
        self.catalog_jobs = JobQueue(self)
        self.catalog_jobs.status.connect(self._catalog_loaded)
        self.catalog_jobs.idle.connect(self._selection_changed)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        title = W.QLabel("Play")
        title.setProperty("role", "title")
        layout.addWidget(title)
        intro = W.QLabel("Choose your decks and start a Unity game against an offline AI opponent.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = W.QFormLayout()
        self.format = W.QComboBox()
        self.format.addItem("Freeform", "freeform")
        self.format.addItem("Commander", "commander")
        self.format.setCurrentIndex(self.format.findData(self.lobby.format))
        self.format.currentIndexChanged.connect(self._selection_changed)
        form.addRow("Format", self.format)
        self.selectors = []
        for label in ("Your deck", "AI opponent deck"):
            selector = W.QComboBox()
            selector.setAccessibleName(label)
            selector.currentIndexChanged.connect(self._selection_changed)
            form.addRow(label, selector)
            self.selectors.append(selector)
        self.unity_payment_mode = W.QComboBox()
        self.unity_payment_mode.setAccessibleName("Unity mana payment")
        for label, mode in (("Auto mana", "auto"), ("Manual mana", "manual"),
                            ("Full Control", "full-control")):
            self.unity_payment_mode.addItem(label, mode)
        form.addRow("Mana payment", self.unity_payment_mode)
        layout.addLayout(form)
        self.start_button = W.QPushButton("Start Game")
        self.start_button.setProperty("buttonRole", "primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_game)
        layout.addWidget(self.start_button)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        layout.addStretch()
        self.load_decks()

    def load_decks(self):
        if self.busy:
            return
        self.status.setText("Loading saved decks…")
        def work(cancel, report):
            decks, errors = self._deck_provider()
            return prepare_catalog(decks, self.service, cancel=cancel, report=report), errors
        self.catalog_jobs.submit(work, quiet=True)
        self._selection_changed()

    @C.pyqtSlot(str, str, object)
    def _catalog_loaded(self, job, state, value):
        if state == "completed":
            previous = [self._decks[selector.currentData()].key
                        if selector.currentData() is not None else None
                        for selector in self.selectors]
            self._decks, errors = value
            for selector, key in zip(self.selectors, previous) in self.selectors:
                selector.blockSignals(True)
                selector.clear()
                selector.addItem("Choose a saved deck", None)
                for index, deck in enumerate(self._decks):
                    selector.addItem(deck.document.deck.name, index)
                for index, deck in enumerate(self._decks):
                    if deck.key == key:
                        selector.setCurrentIndex(index + 1)
                        break
                selector.blockSignals(False)
            self.status.setText("Some saved decks could not be read. Review them in Deck Editor."
                                if errors else "Choose your deck and the AI opponent's deck."
                                if self._decks else "Save decks in Deck Editor, then return to Play.")
        elif state == "failed":
            self.status.setText("Could not load saved decks. Review them in Deck Editor, then return to Play.")
        self._selection_changed()

    def _selection_changed(self):
        if not hasattr(self, "start_button"):
            return
        busy = self.busy
        self.format.setEnabled(not busy)
        self.unity_payment_mode.setEnabled(not busy)
        lobby = replace(self.lobby, format=self.format.currentData())
        ready = True
        reasons = []
        for seat, selector in zip(lobby.seats, self.selectors):
            selector.setEnabled(not busy)
            index = selector.currentData()
            selection = None
            if index is None:
                ready = False
            else:
                item = self._decks[index]
                check = item.readiness(lobby.format)
                if check is not None and not check.can_start:
                    ready = False
                    reasons.extend(check.messages)
                selection = DeckSelection.local(item.document, owner_id=item.owner_id,
                                                source_id=item.source_id)
            lobby = lobby.select_deck(seat.seat_id, selection)
        self.lobby = lobby
        self.start_button.setEnabled(ready and not busy)
        if not busy:
            if reasons:
                self.status.setText("\n".join(dict.fromkeys(reasons)))
            elif ready:
                self.status.setText("Ready to start your Unity game.")

    def _status(self, message):
        self.status.setText(message)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.busy:
            self.load_decks()

    def start_game(self):
        if not self.start_button.isEnabled():
            return
        from mtg_proxy.constants import APP_VERSION

        setup = self.lobby.offline_setup()
        payment_mode = self.unity_payment_mode.currentData()
        deck_owners = {seat.seat_id: seat.deck.owner_id for seat in self.lobby.seats}
        documents = {
            seat.seat_id: deepcopy(seat.deck.document) for seat in self.lobby.seats
        }
        sources = {
            seat.seat_id: self._decks[selector.currentData()].path
            for seat, selector in zip(self.lobby.seats, self.selectors)
        }
        self._native_launch = launch = LiveGameLaunch()

        def work(cancel, report):
            from mtg_core.decks import DeckStore

            for seat, path in sources.items():
                if path is not None:
                    try:
                        selected = DeckStore().load(path)
                    except Exception:
                        raise ValueError("UNITY_GAME_DECK_UNREADABLE") from None
                    if selected.deck.deck_id != documents[seat].deck.deck_id:
                        raise ValueError("UNITY_GAME_DECK_CHANGED")
                    documents[seat] = selected
            return run_live_game(
                setup,
                documents,
                cancel,
                report,
                version=APP_VERSION,
                launch=launch,
                payment_mode=payment_mode,
                deck_owners=deck_owners,
            )

        self.native_jobs.submit(work, quiet=True)
        self._selection_changed()

    def _close_unity_game(self):
        if self.native_jobs.busy:
            self.native_jobs.cancel_all()
        elif self._native_launch is not None and self._native_launch.root is not None:
            launch = self._native_launch
            self.native_jobs.submit(lambda cancel, report: launch.close(), quiet=True)
        self._selection_changed()

    @C.pyqtSlot(str, object)
    def _native_progress(self, job, value):
        if isinstance(value, dict) and isinstance(value.get("phase"), str):
            self._status(value["phase"])

    @C.pyqtSlot(str, str, object)
    def _native_status(self, job, state, value):
        if state == "failed":
            self._status(
                {
                    "UNITY_GAME_BUILD_MISSING": "Build the Windows Play player before starting a Unity game.",
                    "UNITY_GAME_PRINTING_UNSUPPORTED": "A card could not be resolved by XMage.",
                    "UNITY_GAME_CARD_UNSUPPORTED": "XMage does not support a card in the selected decks.",
                    "UNITY_GAME_CARD_RESOLUTION_FAILED": "XMage could not resolve the selected cards. Please try again.",
                    "UNITY_GAME_SETUP_UNSUPPORTED": "Unity gameplay supports Freeform or Commander 1v1 with one human and one AI.",
                }.get(
                    value,
                    "Unity game stopped or could not start. Saved decks are unchanged.",
                )
            )
        elif state in {"completed", "cancelled"}:
            outcome = value.get("outcome") if isinstance(value, dict) else None
            self._status(
                "Unity game result: " + outcome
                if outcome in ("win", "loss", "draw")
                else "Unity game closed. Deck selections are unchanged."
            )

    def prepare_to_close(self):
        if self.native_jobs.busy or (self._native_launch is not None
                                     and self._native_launch.root is not None):
            self._close_unity_game()
            return False
        if self.catalog_jobs.busy:
            self.catalog_jobs.cancel_all()
            return False
        return True

    @property
    def busy(self):
        return (self.native_jobs.busy or self.catalog_jobs.busy
                or (self._native_launch is not None and self._native_launch.root is not None))
