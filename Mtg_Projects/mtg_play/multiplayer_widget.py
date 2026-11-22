"""Desktop lobby controls. All game decisions remain in Unity and Java."""

from copy import deepcopy
import os
import threading
import uuid
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_ui.jobs import JobQueue
from .contracts import GameSetup, MatchSeat, ADAPTER_VERSION
from .live_game import LiveGameLaunch
from .multiplayer import (
    MultiplayerLobby,
    SHARED_RELAY_URL,
    new_code,
    invite,
    parse_invite,
    relay_url,
    export_remote_deck,
    import_remote_deck,
)
from .relay_client import RelayClient, LoopbackTunnel
from .multiplayer_runtime import run_host_game, run_guest_game
from .recovery import RecoveryMailbox


class MultiplayerPanel(W.QWidget):
    prepare_remote = C.pyqtSignal(object, int)
    tunnel_failed = C.pyqtSignal(str)

    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.relay = None
        self.model = None
        self.view = None
        self.hosting = False
        self.tunnel = None
        self.target_port = None
        self.launch = None
        self.started = False
        self.finished = False
        self.normal_result = False
        self.failure_code = None
        self.admitted = False
        self.remote_finished = threading.Event()
        self.recovery_mailbox = RecoveryMailbox()
        self.recovery_state = None
        self.guest_peer = "guest"
        self.claim_peer = None
        self.claim_ticket = None
        self.waiting_peers = set()
        self.reconnect_pending = False
        self.returning_to_lobby = False
        self.jobs = JobQueue(self)
        self.jobs.progress.connect(self._progress)
        self.jobs.status.connect(self._status)
        self.jobs.idle.connect(self.render)
        self.prepare_remote.connect(self._prepare_remote)
        self.tunnel_failed.connect(self.on_tunnel_failed)
        layout = W.QVBoxLayout(self)
        self.endpoint = W.QLineEdit(
            C.QSettings().value(
                "play/relayUrl", os.environ.get("MANAFORGE_RELAY_URL", SHARED_RELAY_URL)
            )
        )
        self.endpoint.setPlaceholderText("wss://your-relay.workers.dev")
        self.endpoint.setAccessibleName("Multiplayer relay URL")
        network = W.QToolButton()
        network.setText("Relay settings")
        network.setCheckable(True)
        network.toggled.connect(self.endpoint.setVisible)
        layout.addWidget(network)
        layout.addWidget(self.endpoint)
        self.endpoint.hide()
        self.code = W.QLineEdit()
        self.code.setPlaceholderText("Join code or Manaforge invitation")
        self.code.setAccessibleName("Join code or invitation")
        layout.addWidget(self.code)
        buttons = W.QHBoxLayout()
        self.host = W.QPushButton("Host Game")
        self.join = W.QPushButton("Join Game")
        self.copy_code = W.QPushButton("Copy Code")
        self.copy_invite = W.QPushButton("Copy Invite")
        self.leave = W.QPushButton("Leave Lobby")
        for button in (
            self.host,
            self.join,
            self.copy_code,
            self.copy_invite,
            self.leave,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.host.clicked.connect(lambda: self.connect_room(True))
        self.join.clicked.connect(lambda: self.connect_room(False))
        self.copy_code.clicked.connect(
            lambda: W.QApplication.clipboard().setText(
                self.relay.code if self.relay else ""
            )
        )
        self.copy_invite.clicked.connect(
            lambda: (
                W.QApplication.clipboard().setText(
                    invite(self.relay.endpoint, self.relay.code)
                )
                if self.relay
                else None
            )
        )
        self.leave.clicked.connect(self.reset)
        self.rows = []
        self.selectors = []
        for index in range(2):
            row = W.QHBoxLayout()
            label = W.QLabel()
            kind = W.QComboBox()
            kind.addItem("Open", "open")
            kind.addItem("AI", "ai")
            selector = W.QComboBox()
            selector.setAccessibleName("Seat " + str(index + 1) + " deck")
            row.addWidget(label)
            row.addWidget(kind)
            row.addWidget(selector)
            layout.addLayout(row)
            kind.currentIndexChanged.connect(lambda _, i=index: self.change_kind(i))
            selector.currentIndexChanged.connect(lambda _, i=index: self.select_deck(i))
            self.rows.append((label, kind))
            self.selectors.append(selector)
        self.remove = W.QPushButton("Remove Guest")
        self.remove.clicked.connect(self.remove_guest)
        layout.addWidget(self.remove)
        self.ready = W.QPushButton("Ready")
        self.ready.clicked.connect(self.toggle_ready)
        layout.addWidget(self.ready)
        self.start = W.QPushButton("Start Game")
        self.start.clicked.connect(self.start_game)
        layout.addWidget(self.start)
        self.message = W.QLabel(
            "Host a game or enter a friend's invitation. Custom relays must support the Manaforge protocol."
        )
        self.message.setWordWrap(True)
        self.message.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.seat_picker = W.QGroupBox("Join game in progress")
        picker = W.QVBoxLayout(self.seat_picker)
        self.seat_details = W.QLabel()
        self.seat_details.setTextFormat(C.Qt.TextFormat.PlainText)
        self.seat_details.setWordWrap(True)
        picker.addWidget(self.seat_details)
        self.claim_seat = W.QPushButton("Take seat 2")
        self.claim_seat.clicked.connect(self.claim_active_seat)
        picker.addWidget(self.claim_seat)
        layout.addWidget(self.seat_picker)
        self.reconnect_button = W.QPushButton("Reconnect")
        self.reconnect_button.clicked.connect(self.reconnect_game)
        layout.addWidget(self.reconnect_button)
        self.refresh_decks()
        self.render()

    @property
    def busy(self):
        return (
            self.jobs.busy or self.launch is not None and self.launch.root is not None
        )

    def refresh_decks(self):
        previous = getattr(self, "_deck_keys", [])
        current = [deck.key for deck in self.workspace._decks]
        cleared = []
        for seat, selector in enumerate(self.selectors):
            old = selector.currentData()
            key = previous[old] if old is not None and old < len(previous) else None
            selector.blockSignals(True)
            selector.clear()
            selector.addItem("Choose a saved deck", None)
            for index, deck in enumerate(self.workspace._decks):
                selector.addItem(deck.document.deck.name, index)
            if key is not None and key in current:
                selector.setCurrentIndex(current.index(key) + 1)
            elif key is not None:
                cleared.append(seat)
            selector.blockSignals(False)
        self._deck_keys = current
        for seat in cleared:
            self.select_deck(seat)

    def connect_room(self, hosting):
        if self.relay and not self.relay.closed or self.busy:
            return
        if self.relay:
            self.relay.deleteLater()
            self.relay = None
        try:
            development = os.environ.get("MANAFORGE_RELAY_DEVELOPMENT") == "1"
            endpoint, code = (
                (relay_url(self.endpoint.text(), development=development), new_code())
                if hosting
                else parse_invite(
                    self.code.text(), self.endpoint.text(), development=development
                )
            )
            self.hosting = hosting
            self.started = self.finished = self.admitted = self.normal_result = False
            self.failure_code = None
            self.recovery_state = None
            self.claim_peer = None
            self.claim_ticket = None
            self.guest_peer = "guest"
            self.waiting_peers.clear()
            self.reconnect_pending = False
            self.recovery_mailbox = RecoveryMailbox()
            self.remote_finished.clear()
            self.model = (
                MultiplayerLobby(self.workspace.format.currentData())
                if hosting
                else None
            )
            self.view = self.model.public() if hosting else None
            self.relay = RelayClient(
                endpoint, code, hosting, self, development=development
            )
            self.relay.message_received.connect(self.receive)
            self.relay.failed.connect(self.fail)
            self.endpoint.setText(endpoint)
            C.QSettings().setValue("play/relayUrl", endpoint)
            self.relay.open()
            self.message.setText("Connecting to relay…")
            self.render()
        except (ValueError, TypeError):
            self.message.setText(
                "Enter a valid WSS relay URL and join code or invitation."
            )

    def send_lobby(self):
        self.view = self.model.public()
        if self.admitted and self.model.seats[1].kind == "human":
            from mtg_proxy.constants import APP_VERSION

            self.relay.payload(
                {
                    "type": "lobby",
                    "version": APP_VERSION,
                    "adapter": ADAPTER_VERSION,
                    "lobby": self.view,
                },
                self.guest_peer,
            )
        self.render()

    def receive(self, message):
        try:
            op = message.get("op")
            if op == "admitted":
                if message.get("recovery_version") != 1:
                    self.fail("RELAY_UPGRADE_REQUIRED")
                    return
                self.admitted = True
                if self.hosting:
                    self.code.setText(self.relay.code)
                self.message.setText(
                    "Join code: " + self.relay.code
                    if self.hosting
                    else "Connected. Waiting for the host's lobby…"
                )
                if self.hosting:
                    for i in range(2):
                        if (
                            self.selectors[i].currentData() is not None
                            and self.model.seats[i].kind != "open"
                        ):
                            self.select_deck(i)
            elif op == "joined" and self.hosting:
                self.waiting_peers.add(message["peer"])
                if self.started:
                    self.send_match(message["peer"])
                    return
                if self.model.seats[1].kind != "open":
                    self.relay.send({"op": "kick", "peer": message["peer"]})
                else:
                    self.model.join()
                    self.send_lobby()
            elif op == "left" and self.hosting:
                self.waiting_peers.discard(message["peer"])
                if self.started:
                    peer = message["peer"]
                    self.waiting_peers.discard(peer)
                    if peer == self.guest_peer or peer == self.claim_peer:
                        self.claim_peer = None
                        self.claim_ticket = None
                        if self.tunnel:
                            self.tunnel.close()
                            self.tunnel = None
                        self.recovery_mailbox.send("disconnect")
                    return
                if self.model.seats[1].kind == "human":
                    self.model.leave()
                    self.send_lobby()
            elif op == "message":
                payload = message.get("payload")
                if not isinstance(payload, dict):
                    if self.hosting and self.started:
                        self.relay.send({"op": "kick", "peer": message.get("peer")})
                        return
                    raise ValueError("INVALID_MESSAGE")
                kind = payload.get("type")
                peer = message.get("peer", "guest")
                if (
                    self.hosting
                    and self.started
                    and peer != self.guest_peer
                    and kind != "claim_seat"
                ):
                    self.relay.send({"op": "kick", "peer": peer})
                    return
                if kind == "claim_seat" and self.hosting and self.started:
                    from mtg_proxy.constants import APP_VERSION

                    if (
                        payload.get("version") != APP_VERSION
                        or payload.get("adapter") != ADAPTER_VERSION
                    ):
                        self.relay.payload(
                            {
                                "type": "claim_rejected",
                                "reason": "Both players need the same Manaforge version.",
                            },
                            peer,
                        )
                    elif (
                        payload.get("seat_id") != self.model.seats[1].seat_id
                        or self.claim_peer
                        or not (self.recovery_state or {}).get("claimable")
                    ):
                        self.relay.payload(
                            {
                                "type": "claim_rejected",
                                "reason": "That seat is no longer available.",
                            },
                            peer,
                        )
                    else:
                        self.claim_peer = peer
                        self.claim_ticket = uuid.uuid4().hex
                        self.recovery_mailbox.send(
                            {"action": "claim", "ticket": self.claim_ticket}
                        )
                    return
                elif kind == "match" and not self.hosting:
                    self.recovery_state = payload["recovery"]
                    root = self.launch.root if self.launch else None
                    if root:
                        from .recovery import atomic_json

                        try:
                            atomic_json(
                                root / "recovery-state.json", self.recovery_state
                            )
                        except OSError:
                            pass  # The departing Unity process may already have finished cleanup.
                    self.render()
                    return
                elif kind == "claim_rejected" and not self.hosting:
                    self.message.setText(payload.get("reason", "Seat unavailable."))
                    self.claim_seat.setEnabled(True)
                    return
                elif (
                    kind == "frame"
                    and self.tunnel
                    and (not self.hosting or peer == self.guest_peer)
                ):
                    self.tunnel.feed(payload)
                elif (
                    kind == "tunnel_open"
                    and self.hosting
                    and self.started
                    and self.target_port
                    and self.tunnel is None
                    and peer == self.guest_peer
                ):
                    self.tunnel = LoopbackTunnel(
                        lambda value, target=peer: self.relay.payload(value, target),
                        self.tunnel_failed.emit,
                        target_port=self.target_port,
                    )
                elif (
                    kind == "select"
                    and self.hosting
                    and not self.started
                    and self.model.seats[1].kind == "human"
                ):
                    from mtg_proxy.constants import APP_VERSION

                    if (
                        payload.get("version") != APP_VERSION
                        or payload.get("adapter") != ADAPTER_VERSION
                    ):
                        raise ValueError("INCOMPATIBLE_VERSION")
                    if payload["deck"] is None:
                        self.model.clear(1)
                    else:
                        self.model.select(
                            1,
                            import_remote_deck(payload["deck"], self.model.format),
                            payload.get("payment", "auto"),
                        )
                    self.send_lobby()
                elif kind == "ready" and self.hosting and not self.started:
                    self.model.ready(1, payload.get("ready"))
                    self.send_lobby()
                elif kind == "lobby" and not self.hosting and not self.started:
                    from mtg_proxy.constants import APP_VERSION

                    if (
                        payload.get("version") != APP_VERSION
                        or payload.get("adapter") != ADAPTER_VERSION
                    ):
                        raise ValueError("INCOMPATIBLE_VERSION")
                    view = payload["lobby"]
                    if (
                        view.get("format")
                        not in ("freeform", "commander", "unrestricted_commander")
                        or len(view.get("seats", [])) != 2
                        or any(
                            s.get("kind") not in ("open", "ai", "human")
                            for s in view["seats"]
                        )
                    ):
                        raise ValueError("INVALID_LOBBY")
                    first = self.view is None
                    self.view = view
                    self.message.setText(
                        "Online lobby · " + view["format"].replace("_", " ")
                    )
                    if first and self.selectors[1].currentData() is not None:
                        self.select_deck(1)
                elif kind == "return_to_lobby" and not self.hosting:
                    self.return_to_lobby(
                        payload.get(
                            "message", "Game ended. Ready up for another game."
                        ),
                        notify=False,
                    )
                elif kind == "game_interrupted" and self.hosting and self.started:
                    self.return_to_lobby(
                        "Game interrupted. The lobby and decks have been kept."
                    )
                elif kind == "prepare" and not self.hosting and not self.busy:
                    self.start_guest(payload)
                elif kind == "recovery_ended" and not self.hosting:
                    if self.launch and self.launch.root:
                        from .recovery import atomic_json

                        atomic_json(
                            self.launch.root / "recovery-state.json", {"ended": True}
                        )
                    self.message.setText("The host ended the game without a winner.")
                elif kind == "finished":
                    # Let Unity consume the result and finish its private cleanup before closing transport.
                    self.message.setText(
                        "Other player finished. Close Unity to return to setup."
                    )
                    self.remote_finished.set()
                else:
                    raise ValueError("MESSAGE_UNSUPPORTED")
            self.render()
        except (ValueError, TypeError, KeyError, IndexError):
            if self.hosting and self.started and message.get("op") == "message":
                self.relay.send({"op": "kick", "peer": message.get("peer")})
                return
            self.fail("LOBBY_MESSAGE_REJECTED")

    def change_kind(self, index):
        if self.model and self.hosting and self.admitted and not self.started:
            try:
                self.model.set_kind(index, self.rows[index][1].currentData())
                self.select_deck(index)
                self.send_lobby()
            except ValueError:
                self.render()

    def select_deck(self, index):
        if not self.relay or not self.admitted or self.started:
            return
        selected = self.selectors[index].currentData()
        try:
            if selected is None:
                if self.hosting and self.model.seats[index].kind != "open":
                    self.model.clear(index)
                    self.send_lobby()
                elif not self.hosting:
                    from mtg_proxy.constants import APP_VERSION

                    self.relay.payload(
                        {
                            "type": "select",
                            "deck": None,
                            "version": APP_VERSION,
                            "adapter": ADAPTER_VERSION,
                        }
                    )
                    self.ready.setEnabled(False)
                return
            document = self.workspace._decks[selected].document
            payment = self.workspace.unity_payment_mode.currentData()
            if self.hosting and (index == 0 or self.model.seats[index].kind == "ai"):
                self.model.select(index, document, payment)
                self.send_lobby()
            elif not self.hosting and index == 1 and self.view:
                from mtg_proxy.constants import APP_VERSION

                self.relay.payload(
                    {
                        "type": "select",
                        "deck": export_remote_deck(document, self.view["format"]),
                        "payment": payment,
                        "version": APP_VERSION,
                        "adapter": ADAPTER_VERSION,
                    }
                )
        except (ValueError, TypeError):
            if self.hosting:
                self.model.clear(index)
                self.send_lobby()
            else:
                from mtg_proxy.constants import APP_VERSION

                self.relay.payload(
                    {
                        "type": "select",
                        "deck": None,
                        "version": APP_VERSION,
                        "adapter": ADAPTER_VERSION,
                    }
                )
            self.message.setText("This deck cannot be used in the selected format.")

    def toggle_ready(self):
        if not self.view or self.started:
            return
        index = 0 if self.hosting else 1
        if self.hosting:
            try:
                self.model.ready(index, not self.model.seats[index].ready)
                self.send_lobby()
            except ValueError:
                self.message.setText("Choose a valid deck before readying up.")
        else:
            self.relay.payload(
                {"type": "ready", "ready": not self.view["seats"][1]["ready"]}
            )

    def remove_guest(self):
        if self.model and self.model.seats[1].kind == "human" and not self.started:
            self.relay.send({"op": "kick"})

    def start_game(self):
        if not self.model or not self.model.can_start or self.busy:
            return
        from mtg_proxy.constants import APP_VERSION

        self.model.start()
        self.returning_to_lobby = False
        self.remote_finished = threading.Event()
        self.recovery_mailbox = RecoveryMailbox()
        self.started = True
        self.view = self.model.public()
        self.relay.send({"op": "start"})
        setup = GameSetup(
            tuple(
                MatchSeat(
                    s.seat_id, s.name, "engine_ai" if s.kind == "ai" else "local_human"
                )
                for s in self.model.seats
            ),
            format=self.model.format,
        )
        documents = {s.seat_id: deepcopy(s.deck) for s in self.model.seats}
        modes = tuple(s.payment for s in self.model.seats)
        self.launch = LiveGameLaunch()
        launch = self.launch

        def work(cancel, report):
            return run_host_game(
                setup,
                documents,
                cancel,
                report,
                version=APP_VERSION,
                launch=launch,
                payment_modes=modes,
                remote_prepare=self.prepare_remote.emit,
                remote_finished=self.remote_finished,
                recovery_mailbox=self.recovery_mailbox,
            )

        self.jobs.submit(work, quiet=True)
        self.render()

    @C.pyqtSlot(object, int)
    def _prepare_remote(self, payload, port):
        if self.relay and not self.relay.closed and self.started:
            if payload.get("claim_ticket") and (
                not self.claim_peer or payload["claim_ticket"] != self.claim_ticket
            ):
                self.recovery_mailbox.send("disconnect")
                return
            if self.claim_peer:
                previous = self.guest_peer
                self.guest_peer = self.claim_peer
                self.claim_peer = None
                self.claim_ticket = None
                if previous != self.guest_peer and previous in self.waiting_peers:
                    self.relay.send({"op": "kick", "peer": previous})
                if self.tunnel:
                    self.tunnel.close()
                    self.tunnel = None
            self.target_port = port
            self.relay.payload(payload, self.guest_peer)

    def start_guest(self, payload):
        self.started = True
        self.finished = self.reconnect_pending = False
        self.returning_to_lobby = False
        self.failure_code = None
        if self.tunnel:
            self.tunnel.close()
        self.tunnel = LoopbackTunnel(self.relay.payload, self.tunnel_failed.emit)
        self.launch = launch = LiveGameLaunch()
        self.jobs.submit(
            lambda cancel, report: run_guest_game(
                payload, self.tunnel.port, cancel, report, launch=launch
            ),
            quiet=True,
        )

    def send_match(self, peer):
        if self.relay and self.recovery_state:
            self.relay.payload({"type": "match", "recovery": self.recovery_state}, peer)

    def claim_active_seat(self):
        if self.relay and not self.relay.closed and self.recovery_state:
            from mtg_proxy.constants import APP_VERSION

            self.relay.payload(
                {
                    "type": "claim_seat",
                    "seat_id": "two",
                    "version": APP_VERSION,
                    "adapter": ADAPTER_VERSION,
                }
            )
            self.claim_seat.setEnabled(False)
            self.message.setText("Connecting to the selected seat…")

    def reconnect_game(self):
        if self.busy:
            return
        if self.relay and not self.relay.closed:
            self.reconnect_pending = False
            self.render()
        else:
            self.connect_room(False)

    def render(self):
        active = self.relay is not None and not self.relay.closed
        recovery = self.recovery_state or {}
        self.seat_picker.setVisible(
            bool(
                not self.hosting
                and recovery
                and not self.busy
                and not self.reconnect_pending
            )
        )
        lines = []
        for index, seat in enumerate(recovery.get("seats", [])):
            state = (
                "Connected host"
                if index == 0
                else "AI · Hardest"
                if recovery.get("controller") == "ai"
                else "Connected"
                if recovery.get("connected")
                else "Disconnected"
            )
            details = f"Seat {index + 1}: {seat['name']} · {state}"
            if seat.get("life") is not None:
                details += f" · {seat['life']} life"
            if seat.get("commanders"):
                details += " · " + ", ".join(seat["commanders"])
            lines.append(details)
        self.seat_details.setText("\n".join(lines))
        self.claim_seat.setEnabled(bool(active and recovery.get("claimable")))
        self.claim_seat.setText(
            "Rejoin seat 2"
            if self.started and recovery.get("controller") == "human"
            else "Take seat 2"
        )
        self.reconnect_button.setVisible(
            bool(self.reconnect_pending and not self.hosting)
        )
        self.reconnect_button.setEnabled(not self.busy)
        for button in (self.host, self.join):
            button.setEnabled(not active and not self.busy and not self.started)
        self.endpoint.setEnabled(not active and not self.busy)
        self.code.setReadOnly(active)
        for button in (self.copy_code, self.copy_invite):
            button.setEnabled(active and self.admitted)
        self.leave.setEnabled(active or self.busy or self.started or self.finished)
        self.start.setVisible(self.hosting)
        self.start.setEnabled(
            bool(
                self.hosting
                and self.admitted
                and self.model
                and self.model.can_start
                and not self.busy
            )
        )
        self.remove.setVisible(
            bool(self.hosting and self.model and self.model.seats[1].kind == "human")
        )
        self.remove.setEnabled(not self.started)
        for i, (label, kind) in enumerate(self.rows):
            s = (
                self.view["seats"][i]
                if self.view
                else {
                    "kind": "open",
                    "name": "Available",
                    "deck_selected": False,
                    "ready": False,
                }
            )
            label.setText(
                "Seat "
                + str(i + 1)
                + ": "
                + s["name"]
                + (
                    " · Ready"
                    if s["ready"]
                    else " · Deck selected"
                    if s["deck_selected"]
                    else ""
                )
            )
            kind.blockSignals(True)
            kind.setCurrentIndex(max(0, kind.findData(s["kind"])))
            kind.blockSignals(False)
            kind.setVisible(self.hosting and i > 0 and s["kind"] != "human")
            kind.setEnabled(self.admitted and not self.started)
            local = (
                self.hosting
                and (i == 0 or s["kind"] == "ai")
                or not self.hosting
                and i == 1
            )
            self.selectors[i].setVisible(local)
            self.selectors[i].setEnabled(
                bool(
                    active
                    and self.admitted
                    and self.view
                    and local
                    and not self.started
                )
            )
        index = 0 if self.hosting else 1
        ready = bool(self.view and self.view["seats"][index]["ready"])
        self.ready.setText("Not Ready" if ready else "Ready")
        self.ready.setEnabled(
            bool(
                active
                and self.admitted
                and not self.started
                and self.view
                and self.view["seats"][index]["deck_selected"]
                and self.selectors[index].currentData() is not None
            )
        )
        self.workspace.format.setEnabled(not self.busy)
        self.workspace.mode.setEnabled(not self.busy)
        self.workspace.player_count.setEnabled(not self.busy)
        self.workspace.unity_payment_mode.setEnabled(not self.busy and not self.started)

    def _progress(self, job, value):
        if self.returning_to_lobby:
            return
        if (
            self.started
            and self.hosting
            and isinstance(value, dict)
            and isinstance(value.get("recovery"), dict)
        ):
            self.recovery_state = value["recovery"]
            if self.claim_peer and (
                self.recovery_state.get("error")
                or self.recovery_state.get("finished")
                or self.recovery_state.get("ended")
            ):
                self.relay.payload(
                    {
                        "type": "claim_rejected",
                        "reason": self.recovery_state.get("error")
                        or "This game has ended.",
                    },
                    self.claim_peer,
                )
                self.claim_peer = None
                self.claim_ticket = None
            if self.relay and not self.relay.closed:
                for peer in self.waiting_peers:
                    self.send_match(peer)
            self.render()
        if isinstance(value, dict) and isinstance(value.get("phase"), str):
            self.message.setText(value["phase"])

    def _status(self, job, state, value):
        if state in ("completed", "failed", "cancelled"):
            if self.returning_to_lobby:
                self.render()
                return
            self.finished = True
            if self.failure_code is not None:
                return
            outcome = value.get("outcome") if isinstance(value, dict) else None
            if not self.started:
                if outcome in ("win", "loss", "draw"):
                    self.normal_result = True
                    self.message.setText("Game result: " + outcome)
                    self.render()
                return
            if (self.recovery_state or {}).get("ended"):
                self.normal_result = True
                self.return_to_lobby(
                    "The host ended the game without a winner. Ready up for another game."
                )
                return
            self.normal_result = outcome in ("win", "loss", "draw")
            if not self.normal_result:
                if not self.hosting and self.started:
                    if self.relay and not self.relay.closed:
                        self.relay.payload({"type": "game_interrupted"})
                        self.return_to_lobby(
                            "Game interrupted. Waiting for the host to reset the lobby.",
                            notify=False,
                        )
                    else:
                        self.connection_lost()
                    return
                self.fail("GAME_INTERRUPTED")
                return
            if (
                self.relay
                and not self.relay.closed
                and (
                    not self.hosting
                    or (self.recovery_state or {}).get("controller") == "human"
                )
            ):
                self.relay.payload(
                    {"type": "finished"}, self.guest_peer if self.hosting else None
                )
            if self.hosting:
                self.return_to_lobby(
                    "Game result: " + outcome + ". Ready up for another game."
                )
            else:
                self.message.setText(
                    "Game result: " + outcome + ". Waiting for the host's lobby."
                )
                self.render()

    @C.pyqtSlot(str)
    def on_tunnel_failed(self, code):
        if self.tunnel is None or self.tunnel.failure_code != code:
            return
        if self.normal_result or (self.recovery_state or {}).get("ended"):
            return
        if self.hosting and self.started:
            if self.tunnel:
                self.tunnel.close()
                self.tunnel = None
            self.recovery_mailbox.send("disconnect")
        else:
            self.fail(code)

    def connection_lost(self):
        self.reconnect_pending = True
        if self.tunnel:
            self.tunnel.close()
            self.tunnel = None
        self.message.setText(
            "Connection lost. Reconnect to choose an available seat, or Leave Lobby."
        )
        self.render()

    @C.pyqtSlot(str)
    def fail(self, code):
        if self.normal_result or self.failure_code is not None:
            return
        if self.started and self.relay and not self.relay.closed:
            if not self.hosting:
                self.relay.payload({"type": "game_interrupted"})
            self.return_to_lobby(
                "Game interrupted: "
                + code.replace("_", " ").lower()
                + ". The lobby and decks have been kept.",
                notify=self.hosting,
            )
            return
        if not self.hosting and self.started:
            self.connection_lost()
            self.jobs.cancel_all()
            return
        # Cancellation can synchronously report SESSION_EOF. Retain the cause
        # that prompted cleanup rather than replacing it with GAME_INTERRUPTED.
        self.failure_code = code
        self.finished = True
        self.jobs.cancel_all()
        if self.tunnel:
            self.tunnel.close()
            self.tunnel = None
        if self.relay:
            self.relay.close()
        self.admitted = False
        self.message.setText(
            {
                "INCOMPATIBLE_VERSION": "Both players need the same Manaforge version.",
                "RELAY_UPGRADE_REQUIRED": "This relay needs the reconnect update. Use an updated relay to host or join a game.",
                "RELAY_CERTIFICATE_FAILED": "The relay's TLS certificate could not be verified.",
                "ROOM_UNAVAILABLE": "That room is full, expired, or already playing.",
            }.get(
                code,
                "Game interrupted: "
                + code.replace("_", " ").lower()
                + ". You can create or join another lobby.",
            )
        )
        self.render()

    def return_to_lobby(self, message, *, notify=True):
        self.returning_to_lobby = True
        self.started = self.finished = self.normal_result = False
        self.failure_code = None
        self.jobs.cancel_all()
        if self.tunnel:
            self.tunnel.close()
            self.tunnel = None
        self.target_port = None
        self.recovery_state = None
        self.claim_peer = self.claim_ticket = None
        self.reconnect_pending = False
        if self.hosting and self.model:
            self.model.return_to_lobby()
            self.view = self.model.public()
            if self.relay and not self.relay.closed:
                if notify:
                    self.relay.payload(
                        {"type": "return_to_lobby", "message": message}, self.guest_peer
                    )
                self.send_lobby()
        elif self.view:
            self.view = deepcopy(self.view)
            self.view["started"] = False
            for seat in self.view["seats"]:
                if seat["kind"] == "human":
                    seat["ready"] = False
        self.message.setText(message)
        self.render()

    def reset(self):
        self.returning_to_lobby = True
        self.jobs.cancel_all()
        if self.tunnel:
            self.tunnel.close()
            self.tunnel = None
        if self.relay:
            self.relay.close()
            self.relay.deleteLater()
            self.relay = None
        self.model = self.view = None
        self.admitted = False
        self.target_port = None
        self.started = self.finished = self.normal_result = False
        self.failure_code = None
        self.recovery_state = None
        self.claim_peer = None
        self.claim_ticket = None
        self.guest_peer = "guest"
        self.waiting_peers.clear()
        self.reconnect_pending = False
        self.returning_to_lobby = False
        self.message.setText("Host a game or enter a friend's invitation.")
        self.render()

    def prepare_to_close(self):
        self.reset()
        return not self.busy
