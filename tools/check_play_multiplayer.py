"""Hosted public-deck two-Unity acceptance through a real relay. No user decks."""
import argparse
import json
from pathlib import Path
import sys
import threading
import subprocess
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
from PyQt6 import QtCore as C
from mtg_play.contracts import GameSetup, MatchSeat
from mtg_play.live_game import LiveGameLaunch
from mtg_play.multiplayer import new_code
from mtg_play.multiplayer_runtime import run_host_game, run_guest_game
from mtg_play.relay_client import RelayClient, LoopbackTunnel
from mtg_proxy.constants import APP_VERSION
from mtg_core.decks import Deck, DeckDocument, DeckEntry
from check_play_unity_game import public_deck, public_commander_deck


class Acceptance(C.QObject):
    prepare = C.pyqtSignal(object, int)
    finished = C.pyqtSignal(str, object)
    failed = C.pyqtSignal(str)

    def __init__(self, options, app):
        super().__init__()
        self.options, self.app = options, app
        self.cancel = threading.Event(); self.guest_finished = threading.Event()
        self.results = {}; self.error = None; self.threads = []; self.tunnels = {}; self.port = None
        code = new_code(); self.host = RelayClient(options.relay, code, True, self, development=True); self.guest = RelayClient(options.relay, code, False, self, development=True)
        self.host.event.connect(lambda message: self.receive("host", message)); self.guest.event.connect(lambda message: self.receive("guest", message))
        self.host.failed.connect(self.fail); self.guest.failed.connect(self.fail); self.failed.connect(self.fail)
        self.prepare.connect(self.remote); self.finished.connect(self.complete)
        self.host.open()

    def receive(self, side, message):
        if message.get("op") == "admitted":
            if side == "host": self.guest.open()
            else: self.thread("host", self.host_game)
        elif message.get("op") == "message":
            payload = message["payload"]
            if payload["type"] == "prepare" and side == "guest":
                self.tunnels[side] = LoopbackTunnel(self.guest.payload, self.failed.emit)
                port = self.tunnels[side].port
                self.thread("guest", lambda: self.guest_game(payload, port))
            elif payload["type"] == "tunnel_open" and side == "host":
                self.tunnels[side] = LoopbackTunnel(self.host.payload, self.failed.emit, target_port=self.port)
            elif payload["type"] == "frame":
                self.tunnels[side].feed(payload)

    def remote(self, payload, port):
        self.port = port; self.host.payload(payload)

    def thread(self, name, work):
        def run():
            try: self.finished.emit(name, work())
            except Exception as error: self.failed.emit(str(error) if str(error).replace("_", "").isalnum() else type(error).__name__)
        worker = threading.Thread(target=run, daemon=True); self.threads.append(worker); worker.start()

    def host_game(self):
        format = self.options.format
        if format == "commander":
            host, guest = public_commander_deck(False), public_commander_deck(True)
        else:
            host = public_deck(False)
            guest = DeckDocument(deck=Deck(name="Public relay defender", entries=[DeckEntry("forest", "Forest", 60, set_code="TRK", collector_number="325")]))
        setup = GameSetup((MatchSeat("one", "Host"), MatchSeat("two", "Guest")), format=format)
        return run_host_game(setup, {"one": host, "two": guest}, self.cancel, lambda _: None, version=APP_VERSION, launch=LiveGameLaunch(), remote_prepare=self.prepare.emit, remote_finished=self.guest_finished, xmage_root=Path(self.options.xmage_root), jdk_path=Path(self.options.jdk_path), acceptance=True)

    def guest_game(self, payload, port):
        # Separate client process/data directory preserves the real component ownership lock.
        with tempfile.TemporaryDirectory(prefix="manaforge-public-guest-") as data:
            child = subprocess.Popen([sys.executable, __file__, "--guest", str(port)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={**os.environ, "PRINT_PROXY_PREP_DATA_DIR": data}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                raw = json.dumps(payload).encode(); child.stdin.write(len(raw).to_bytes(4, "big") + raw); child.stdin.flush()
                while child.poll() is None:
                    if self.cancel.wait(.1):
                        child.stdin.close(); child.wait(timeout=15); break
                output = child.stdout.read(16384)
                if child.returncode != 0: raise ValueError("MULTIPLAYER_GUEST_FAILED")
                return json.loads(output)
            finally:
                if not child.stdin.closed: child.stdin.close()
                if child.poll() is None:
                    try: child.wait(timeout=15)
                    except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)

    def complete(self, side, result):
        self.results[side] = result
        if side == "guest": self.guest_finished.set()
        if len(self.results) == 2:
            self.app.quit()

    def fail(self, code):
        if len(self.results) == 2: return
        self.error = code; self.cancel.set(); self.guest_finished.set(); self.app.quit()


def main():
    if "--guest" in sys.argv:
        stream = sys.stdin.buffer; size = int.from_bytes(stream.read(4), "big")
        if not 1 <= size <= 16384: return 2
        payload = json.loads(stream.read(size)); cancel = threading.Event()
        def lifeline():
            while stream.read(1): pass
            cancel.set()
        threading.Thread(target=lifeline, daemon=True).start()
        result = run_guest_game(payload, int(sys.argv[-1]), cancel, lambda _: None, launch=LiveGameLaunch(), acceptance=True)
        print(json.dumps(result)); return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relay", required=True)
    parser.add_argument("--xmage-root", required=True)
    parser.add_argument("--jdk-path", required=True)
    parser.add_argument("--format", choices=("freeform", "commander"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(); app = C.QCoreApplication([]); proof = Acceptance(options, app)
    timer = C.QTimer(); timer.setSingleShot(True); timer.timeout.connect(lambda: proof.fail("MULTIPLAYER_ACCEPTANCE_TIMEOUT")); timer.start(1200000)
    app.exec(); proof.cancel.set()
    for tunnel in proof.tunnels.values(): tunnel.close()
    proof.host.close(); proof.guest.close()
    for worker in proof.threads: worker.join(30)
    outcomes = sorted(r.get("outcome", "") for r in proof.results.values())
    passed = proof.error is None and outcomes == ["loss", "win"] and all(r.get("viewer_cleared") is True and r.get("cleanup_confirmed") is True and r.get("uncertain") == 0 for r in proof.results.values()) and not any(t.is_alive() for t in proof.threads)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps({"passed": passed, "format": options.format, "outcomes": outcomes, "error": proof.error, "two_physical_computers": False, "normal_gameplay_result": passed, "transport_bytes_by_endpoint": {side: {"sent": tunnel.sent_bytes, "received": tunnel.received_bytes} for side, tunnel in proof.tunnels.items()}}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
