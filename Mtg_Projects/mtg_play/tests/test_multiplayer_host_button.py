"""Real Qt Host Game admission, isolated so Qt callback crashes fail one CI test."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_host_button_survives_qt_events_and_receives_join_code(tmp_path):
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
                    peer.sendTextMessage(json.dumps({{'relay_version': 1, 'op': 'admitted', 'peer': 'host'}}))
            peer.textMessageReceived.connect(receive)
        server.newConnection.connect(connected)

        PlayWorkspace.load_decks = lambda self: None
        widget = PlayWorkspace(None, lambda: None)
        widget.mode.setCurrentIndex(widget.mode.findData('online'))
        panel = widget.multiplayer
        panel.endpoint.setText('ws://127.0.0.1:' + str(server.serverPort()))
        result = {{'passed': False}}

        def inspect():
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
            panel.finished = True
            panel.relay.close()
            panel.render()
            result['passed'] = result['passed'] and panel.leave.isEnabled()
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
