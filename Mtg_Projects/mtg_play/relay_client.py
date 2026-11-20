"""WSS relay and bounded loopback tunnel; never interprets gameplay state."""

import base64
import json
import queue
import re
import socket
import struct
import threading
from urllib.parse import urlencode
from PyQt6 import QtCore as C
from PyQt6.QtWebSockets import QWebSocket
from .multiplayer import relay_url

MAX_FRAME = 1048576
MAX_RELAY = 1500000
MAX_TUNNEL_FRAMES = 128
MAX_TUNNEL_BYTES = 8 * MAX_FRAME


class RelayClient(C.QObject):
    message_received = C.pyqtSignal(object)
    failed = C.pyqtSignal(str)
    outgoing = C.pyqtSignal(object)

    def __init__(self, endpoint, code, hosting, parent=None, *, development=False):
        super().__init__(parent)
        self.endpoint = relay_url(endpoint, development=development)
        self.code, self.hosting, self.closed = code, hosting, False
        self.failure_code = None
        self.socket = QWebSocket(parent=self)
        self.socket.setMaxAllowedIncomingFrameSize(MAX_RELAY)
        self.socket.setMaxAllowedIncomingMessageSize(MAX_RELAY)
        self.socket.connected.connect(
            lambda: self.send({"op": "create" if hosting else "join", "recovery_version": 1})
        )
        self.socket.textMessageReceived.connect(self._receive)
        self.socket.binaryMessageReceived.connect(
            lambda _: self.fail("RELAY_INVALID_MESSAGE")
        )
        self.socket.disconnected.connect(lambda: self.fail("RELAY_DISCONNECTED"))
        self.socket.errorOccurred.connect(
            lambda _: self.fail("RELAY_CONNECTION_FAILED")
        )
        self.socket.sslErrors.connect(lambda _: self.fail("RELAY_CERTIFICATE_FAILED"))
        self.outgoing.connect(self.send, C.Qt.ConnectionType.QueuedConnection)
        self.timeout = C.QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self.fail("RELAY_TIMEOUT"))

    def open(self):
        self.timeout.start(10000)
        self.socket.open(
            C.QUrl(self.endpoint + "/v1/socket?" + urlencode({"room": self.code}))
        )

    @C.pyqtSlot(object)
    def send(self, message):
        if self.closed:
            return
        raw = json.dumps(
            {"relay_version": 1, **message}, ensure_ascii=True, separators=(",", ":")
        )
        if len(raw.encode()) > MAX_RELAY or self.socket.bytesToWrite() > 2 * MAX_RELAY:
            self.fail("RELAY_QUEUE_FULL")
            return
        self.socket.sendTextMessage(raw)

    def payload(self, value, peer=None):
        self.outgoing.emit({"op": "send", "payload": value, **({"peer": peer} if peer else {})})

    def _receive(self, raw):
        try:
            if len(raw.encode()) > MAX_RELAY:
                raise ValueError()
            message = json.loads(raw)
            if not isinstance(message, dict) or message.get("relay_version") != 1:
                raise ValueError()
            if message.get("op") == "admitted":
                self.timeout.stop()
            if message.get("op") in ("error", "closed"):
                code = message.get("code", "RELAY_FAILED")
                self.fail(
                    code
                    if isinstance(code, str)
                    and len(code) < 80
                    and code.replace("_", "").isupper()
                    else "RELAY_FAILED"
                )
                return
            self.message_received.emit(message)
        except (ValueError, TypeError):
            self.fail("RELAY_INVALID_MESSAGE")

    def fail(self, code):
        if not self.closed:
            # A close frame can reach Qt before the relay's final error message.
            reason = self.socket.closeReason()
            if code in ("RELAY_DISCONNECTED", "RELAY_CONNECTION_FAILED") and re.fullmatch(
                r"[A-Z_]{1,79}", reason
            ):
                code = reason
            self.failure_code = code
            try:
                from mtg_core.diagnostics import get_logger

                get_logger(__name__).warning(
                    "Relay stopped code=%s role=%s socket_error=%s close_code=%s",
                    code if re.fullmatch(r"[A-Z_0-9]{1,79}", code) else "RELAY_FAILED",
                    "host" if self.hosting else "guest",
                    self.socket.error().name,
                    self.socket.closeCode().name,
                )
            except Exception:
                pass  # Logging must never prevent transport cleanup.
            self.close()
            self.failed.emit(code)

    def close(self):
        self.closed = True
        self.timeout.stop()
        self.socket.abort()


class LoopbackTunnel:
    """One TCP channel, one reader and writer, ordered bounded relay frames."""

    def __init__(self, send, failed, *, target_port=None):
        self.send, self.failed, self.target = send, failed, target_port
        self.inbound = queue.Queue(maxsize=MAX_TUNNEL_FRAMES)
        self.inbound_lock = threading.Lock()
        self.queued_bytes = 0
        self.failure_code = None
        self.cancel = threading.Event()
        self.socket = None
        self.listener = None
        self.completed = False
        self.sent_bytes = self.received_bytes = 0
        if target_port is None:
            self.listener = socket.socket()
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(1)
            self.listener.settimeout(0.2)
            self.port = self.listener.getsockname()[1]
        else:
            self.port = target_port
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="manaforge-relay-tunnel"
        )
        self.thread.start()

    def feed(self, payload):
        try:
            data = payload.get("data")
            if not isinstance(data, str) or len(data) > 1400000:
                raise ValueError()
            raw = base64.b64decode(data, validate=True)
            if not 1 <= len(raw) <= MAX_FRAME:
                raise ValueError()
            with self.inbound_lock:
                if self.cancel.is_set():
                    return
                if self.queued_bytes + len(raw) > MAX_TUNNEL_BYTES:
                    raise queue.Full()
                self.inbound.put_nowait(raw)
                self.queued_bytes += len(raw)
                self.received_bytes += len(raw)
            self._observe_terminal(raw)
        except queue.Full:
            self._fail("TUNNEL_INPUT_OVERFLOW")
        except (ValueError, TypeError, AttributeError):
            self._fail("TUNNEL_INVALID_FRAME")

    def _fail(self, code):
        with self.inbound_lock:
            if self.cancel.is_set() or self.failure_code is not None:
                return
            self.failure_code = code
            queued_bytes = self.queued_bytes
        try:
            from mtg_core.diagnostics import get_logger

            get_logger(__name__).warning(
                "Multiplayer tunnel stopped code=%s queued_frames=%s queued_bytes=%s",
                code,
                self.inbound.qsize(),
                queued_bytes,
            )
        except Exception:
            pass  # Diagnostic storage must not prevent closing a failed transport.
        try:
            self.failed(code)
        finally:
            self.close()

    def _exact(self, count):
        data = bytearray()
        while len(data) < count and not self.cancel.is_set():
            part = self.socket.recv(count - len(data))
            if not part:
                raise OSError()
            data.extend(part)
        if len(data) != count:
            raise OSError()
        return data

    def _run(self):
        try:
            if self.target is None:
                while not self.cancel.is_set():
                    try:
                        self.socket, _ = self.listener.accept()
                        break
                    except socket.timeout:
                        continue
                if self.socket is None:
                    return
                self.send({"type": "tunnel_open"})
            else:
                self.socket = socket.create_connection(
                    ("127.0.0.1", self.target), timeout=5
                )
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.settimeout(30)
            writer = threading.Thread(
                target=self._write, daemon=True, name="manaforge-relay-writer"
            )
            writer.start()
            while not self.cancel.is_set():
                # Idle does not expire a turn; partial frames do.
                self.socket.settimeout(None)
                first = self._exact(1)
                self.socket.settimeout(10)
                length = struct.unpack(">I", first + self._exact(3))[0]
                if not 1 <= length <= MAX_FRAME:
                    raise ValueError()
                raw = self._exact(length)
                self._observe_terminal(raw)
                self.sent_bytes += len(raw)
                self.send(
                    {"type": "frame", "data": base64.b64encode(raw).decode("ascii")}
                )
        except (OSError, ValueError):
            if not self.cancel.is_set() and not self.completed:
                self._fail("GAME_INTERRUPTED")
        finally:
            self.close()

    def _write(self):
        try:
            while not self.cancel.is_set():
                try:
                    raw = self.inbound.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    if not self.cancel.is_set():
                        self.socket.sendall(struct.pack(">I", len(raw)) + raw)
                finally:
                    with self.inbound_lock:
                        self.queued_bytes -= len(raw)
                    self.inbound.task_done()
        except OSError:
            if not self.cancel.is_set() and not self.completed:
                self._fail("GAME_INTERRUPTED")
            self.close()

    def _observe_terminal(self, raw):
        # Transport lifecycle hint only. Unity independently validates/authenticates all frames.
        try:
            self.completed |= json.loads(raw).get("message_type") == "result"
        except (ValueError, AttributeError, UnicodeError):
            pass

    def close(self):
        self.cancel.set()
        with self.inbound_lock:
            while True:
                try:
                    raw = self.inbound.get_nowait()
                except queue.Empty:
                    break
                self.queued_bytes -= len(raw)
                self.inbound.task_done()
        for sock in (self.socket, self.listener):
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
