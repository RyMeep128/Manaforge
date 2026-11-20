"""Host-owned recovery state for an existing two-seat match."""

from dataclasses import dataclass
import json
from pathlib import Path
import queue
import secrets
import time
import uuid


@dataclass
class MatchRecovery:
    paused: bool = False
    controller: str = "human"
    connected: bool = True
    ready: bool = True
    ended: bool = False
    finished: bool = False
    generation: int = 0

    @property
    def claimable(self):
        return (
            not self.ended
            and not self.finished
            and (self.controller == "ai" or not self.connected)
        )

    @property
    def can_resume(self):
        return self.paused and self.ready and not self.ended and not self.finished

    def disconnect(self):
        if self.ended or self.finished or self.controller == "ai":
            return
        self.paused, self.connected, self.ready = True, False, False

    def claim(self):
        if not self.claimable:
            raise ValueError("SEAT_UNAVAILABLE")
        self.generation += 1
        self.paused, self.controller = True, "human"
        self.connected, self.ready = True, False
        return self.generation

    def add_ai(self):
        if self.ended or self.finished or self.connected or self.controller == "ai":
            raise ValueError("SEAT_UNAVAILABLE")
        self.generation += 1
        self.paused, self.controller, self.ready = True, "ai", False

    def resume(self):
        if not self.can_resume:
            raise ValueError("RECOVERY_NOT_READY")
        self.paused = False

    def public(self):
        return dict(
            paused=self.paused,
            controller=self.controller,
            connected=self.connected,
            ready=self.ready,
            ended=self.ended,
            generation=self.generation,
            claimable=self.claimable,
            can_resume=self.can_resume,
            finished=self.finished,
        )


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


class RecoveryMailbox:
    """Thread-safe UI-to-owned-runtime requests. Never carries gameplay answers."""

    def __init__(self):
        self.commands = queue.Queue(maxsize=16)

    def send(self, action):
        try:
            self.commands.put_nowait(action)
        except queue.Full:
            raise ValueError("RECOVERY_BUSY")


class HostRecovery:
    def __init__(
        self,
        root,
        server_process,
        server,
        gateway,
        cancel,
        report,
        mailbox,
        prepare,
        remote_prepare,
        *,
        initial_ai=False,
    ):
        self.root, self.server = Path(root), Path(server)
        self.server_process, self.gateway, self.cancel = server_process, gateway, cancel
        self.report, self.mailbox = report, mailbox
        self.prepare, self.remote_prepare = prepare, remote_prepare
        self.state = MatchRecovery(
            controller="ai" if initial_ai else "human",
            connected=not initial_ai,
            ready=not initial_ai,
        )
        self.initial_ai, self.initialized = initial_ai, False
        self.authenticated = False
        self.last_public = None
        self.error = None
        self.native = None
        self.claim_deadline = None

    def native_command(self, action):
        request_id = str(uuid.uuid4())
        command = dict(
            command="match_recovery",
            request_id=request_id,
            game=self.native["game"],
            action=action,
            seat=self.native["guest_native_id"],
        )
        self.server_process.stdin.write(json.dumps(command) + "\n")
        self.server_process.stdin.flush()
        response = self.server / "manaforge-responses" / (request_id + ".json")
        deadline = time.monotonic() + 5
        while not response.is_file():
            if self.cancel.wait(0.02) or time.monotonic() > deadline:
                raise ValueError("RECOVERY_ENGINE_TIMEOUT")
        value = json.loads(response.read_text(encoding="utf-8"))
        response.unlink()
        if value.get("error"):
            raise ValueError("RECOVERY_ENGINE_REJECTED")
        return value

    def gateway_command(self, action, **extra):
        path = self.root / "recovery-gateway-command.json"
        deadline = time.monotonic() + 5
        while path.exists():
            if self.cancel.wait(0.02) or time.monotonic() > deadline:
                raise ValueError("RECOVERY_GATEWAY_TIMEOUT")
        atomic_json(path, dict(action=action, **extra))
        while path.exists():
            if self.cancel.wait(0.02) or time.monotonic() > deadline:
                raise ValueError("RECOVERY_GATEWAY_TIMEOUT")

    def pause(self):
        self.state.paused = True
        self.gateway_command("pause")
        self.native_command("pause")

    def await_pause(self):
        self.pause()
        deadline = time.monotonic() + 45
        while self.native_command("pause").get("ready") is not True:
            if self.cancel.wait(0.05) or time.monotonic() > deadline:
                raise ValueError("RECOVERY_PAUSE_TIMEOUT")

    def tick(self):
        status = self.root / "recovery-gateway-status.json"
        try:
            self.native = json.loads(status.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        action = None
        claimed = False
        try:
            if not self.initialized:
                self.native_command("status")
                self.initialized = True
                if self.initial_ai:
                    self.pause()
                    self.gateway_command("ai")
            if self.native_command("status").get("ended"):
                self.state.finished = True
                self.state.paused = False
                self.claim_deadline = None
            connected = self.native["connected"]
            if connected:
                self.authenticated = True
                if self.state.controller == "human":
                    self.state.connected = self.state.ready = True
                    self.claim_deadline = None
            elif (
                not self.state.finished
                and self.authenticated
                and self.state.controller == "human"
                and self.state.connected
            ):
                self.state.disconnect()
                self.pause()
            if self.claim_deadline and time.monotonic() > self.claim_deadline:
                self.claim_deadline = None
                self.state.disconnect()
                self.error = (
                    "The replacement did not connect. Choose Reconnect or add AI."
                )
            action_path = self.root / "seat-0" / "recovery-action.json"
            if action_path.is_file():
                action = json.loads(action_path.read_text(encoding="utf-8"))
                action_path.unlink()
                self.mailbox.send(action.get("action"))
            try:
                action = self.mailbox.commands.get_nowait()
            except queue.Empty:
                action = None
            ticket = action.get("ticket") if isinstance(action, dict) else None
            action = action.get("action") if isinstance(action, dict) else action
            if self.state.finished or self.state.ended:
                action = None
            if action == "disconnect":
                if self.state.controller == "human":
                    self.state.disconnect()
                    self.pause()
            elif action == "claim":
                if not self.state.claimable:
                    raise ValueError("SEAT_UNAVAILABLE")
                self.await_pause()
                self.initial_ai = False
                self.state.claim()
                claimed = True
                self.claim_deadline = time.monotonic() + 120
                self.authenticated = False
                self.prepare["viewer_key_hex"] = secrets.token_hex(32)
                self.gateway_command("rotate", key=self.prepare["viewer_key_hex"])
                self.gateway_command("human")
                self.native_command("human")
                self.remote_prepare(dict(self.prepare, claim_ticket=ticket))
            elif action == "add_ai":
                self.state.add_ai()
                self.pause()
                self.gateway_command("rotate", key=secrets.token_hex(32))
                self.gateway_command("ai")
            elif action == "resume":
                if not self.state.can_resume:
                    raise ValueError("RECOVERY_NOT_READY")
                self.native_command("resume")
                self.gateway_command("resume")
                self.state.resume()
            elif action == "end_game":
                self.gateway_command("end")
                self.state.ended = True
            if self.state.paused and not self.state.ended:
                ready = self.native_command("pause").get("ready") is True
                if self.state.controller == "human":
                    self.state.ready = connected and ready
                    if self.state.ready and action is None:
                        self.error = None
                if ready and self.state.controller == "ai":
                    self.native_command("ai")
                    self.state.ready = True
                    if action is None:
                        self.error = None
                    if self.initial_ai:
                        self.initial_ai = False
                        self.native_command("resume")
                        self.gateway_command("resume")
                        self.state.paused = False
            self.error = None if action else self.error
        except (ValueError, OSError, KeyError) as error:
            if claimed:
                self.state.disconnect()
                self.claim_deadline = None
            self.error = (
                str(error)
                if str(error).startswith("RECOVERY_")
                else "Recovery failed. The game remains paused."
            )
            if str(error) == "SEAT_UNAVAILABLE":
                self.error = "That seat is no longer available."
            if str(error) != "SEAT_UNAVAILABLE":
                self.state.paused = True
        public = dict(
            self.state.public(), error=self.error, seats=self.native.get("seats", [])
        )
        public["can_resume"] = public["can_resume"] and self.error is None
        if public != self.last_public:
            try:
                atomic_json(self.root / "seat-0" / "recovery-state.json", public)
            except PermissionError:
                return  # A Windows reader briefly holds the previous complete state.
            self.last_public = public
            self.report({"recovery": public})
