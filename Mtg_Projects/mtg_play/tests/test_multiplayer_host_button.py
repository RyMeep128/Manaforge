"""Real Qt Host Game admission, isolated so Qt callback crashes fail one CI test."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap
import pytest


@pytest.mark.parametrize("outcome", ["win", None])
def test_finished_or_crashed_game_keeps_the_existing_lobby(tmp_path, outcome):
    products = Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        f"""
        import sys
        sys.path[:0] = [{str(products)!r}, {str(products / 'mtg_core')!r}, {str(products / 'mtg_play/tests')!r}]
        from PyQt6 import QtWidgets as W
        from mtg_play.workspace import PlayWorkspace
        from mtg_play.multiplayer import MultiplayerLobby
        from generate_launch_fixtures import native_deck
        app = W.QApplication([])
        PlayWorkspace.load_decks = lambda self: None
        widget = PlayWorkspace(None, lambda: None)
        panel = widget.multiplayer
        class Relay:
            closed = False
            code = 'ABCDEFGHJKLM'
            def __init__(self): self.messages = []
            def payload(self, body, target=None): self.messages.append((body, target))
        relay = Relay()
        panel.relay = relay
        panel.hosting = panel.admitted = True
        panel.guest_peer = 'retained-peer'
        model = panel.model = MultiplayerLobby()
        model.join()
        model.select(0, native_deck(False))
        model.select(1, native_deck(False))
        model.ready(0, True)
        model.ready(1, True)
        decks = [seat.deck for seat in model.seats]
        model.start()
        panel.started = True
        panel._status('fixture', 'completed' if {outcome!r} else 'failed', {{'outcome': {outcome!r}}})
        assert panel.relay is relay and not relay.closed and panel.admitted
        assert panel.model is model and not panel.started and not model.started
        assert [seat.deck for seat in model.seats] == decks
        assert all(not seat.ready for seat in model.seats)
        assert any(body['type'] == 'return_to_lobby' and target == 'retained-peer' for body, target in relay.messages)
        count = len(relay.messages)
        panel._status('late-cancelled-job', 'failed', 'SESSION_EOF')
        assert len(relay.messages) == count
        model.ready(0, True)
        model.ready(1, True)
        assert model.can_start
        panel.relay = None
        panel.reset()
        print('LOBBY_RETAINED')
        """
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=20,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PRINT_PROXY_PREP_DATA_DIR": str(tmp_path)},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "LOBBY_RETAINED" in completed.stdout


@pytest.mark.parametrize("failure_mode", ["message", "close"])
def test_host_button_survives_qt_events_and_receives_join_code(tmp_path, failure_mode):
    products = Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        f"""
        import json
        import sys
        sys.path[:0] = [{str(products)!r}, {str(products / "mtg_core")!r}]
        from PyQt6 import QtCore as C, QtNetwork as N, QtWidgets as W
        from PyQt6.QtWebSockets import QWebSocketServer
        from mtg_play.workspace import PlayWorkspace

        app = W.QApplication([])
        app.setOrganizationName('ManaforgeCI')
        app.setApplicationName('HostButtonRegression')
        peers = []
        server = QWebSocketServer('Host button fixture', QWebSocketServer.SslMode.NonSecureMode)
        if not server.listen(N.QHostAddress(N.QHostAddress.SpecialAddress.LocalHost), 0):
            raise RuntimeError('FIXTURE_LISTEN_FAILED')

        def connected():
            peer = server.nextPendingConnection()
            peers.append(peer)
            def receive(raw):
                message = json.loads(raw)
                if message.get('relay_version') == 1 and message.get('op') == 'create':
                    peer.sendTextMessage(json.dumps({{'relay_version': 1, 'op': 'admitted', 'peer': 'host', 'recovery_version': 1}}))
            peer.textMessageReceived.connect(receive)
        server.newConnection.connect(connected)

        PlayWorkspace.load_decks = lambda self: None
        widget = PlayWorkspace(None, lambda: None)
        widget.mode.setCurrentIndex(widget.mode.findData('online'))
        panel = widget.multiplayer
        panel.endpoint.setText('ws://127.0.0.1:' + str(server.serverPort()))
        result = {{'passed': False, 'closing': False}}

        def inspect():
            if not result['closing']:
                if not panel.admitted:
                    return
                result['passed'] = (
                    callable(panel.relay.event)
                    and panel.relay.parent() is panel
                    and len(panel.code.text()) == 12
                    and panel.model.seats[0].kind == 'human'
                    and panel.model.seats[1].kind == 'open'
                    and 'Join code:' in panel.message.text()
                )
                result['closing'] = True
                if {failure_mode!r} == 'message':
                    peers[0].sendTextMessage(json.dumps({{'relay_version': 1, 'op': 'error', 'code': 'RATE_LIMIT'}}))
                else:
                    from PyQt6.QtWebSockets import QWebSocketProtocol
                    peers[0].close(QWebSocketProtocol.CloseCode.CloseCodeNormal, 'RATE_LIMIT')
                return
            if panel.failure_code is None:
                return
            first_message = panel.message.text()
            panel._status('fixture', 'failed', 'SESSION_EOF')
            panel.fail('GAME_INTERRUPTED')
            result['passed'] = (result['passed'] and panel.leave.isEnabled()
                and panel.finished and not panel.normal_result and panel.relay.closed
                and not panel.admitted and not panel.remote_finished.is_set()
                and panel.failure_code == panel.relay.failure_code == 'RATE_LIMIT'
                and panel.message.text() == first_message and 'rate limit' in first_message)
            panel.reset()
            result['passed'] = result['passed'] and panel.failure_code is None
            panel._status('fixture', 'completed', {{'outcome': 'win'}})
            panel.fail('RELAY_DISCONNECTED')
            result['passed'] = result['passed'] and panel.message.text() == 'Game result: win'
            panel.reset()
            app.quit()
        poll = C.QTimer()
        poll.timeout.connect(inspect)
        poll.start(20)
        C.QTimer.singleShot(5000, app.quit)
        C.QTimer.singleShot(0, panel.host.click)
        app.exec()
        panel.reset()
        for peer in peers:
            peer.abort()
        server.close()
        widget.deleteLater()
        print('HOST_BUTTON_ADMITTED' if result['passed'] else 'HOST_BUTTON_FAILED')
        sys.exit(0 if result['passed'] else 1)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "MANAFORGE_RELAY_DEVELOPMENT": "1",
            "PRINT_PROXY_PREP_DATA_DIR": str(tmp_path),
        },
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "HOST_BUTTON_ADMITTED" in completed.stdout
