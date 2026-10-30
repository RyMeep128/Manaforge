"""Owned-child lifecycle foundation, not a live game launcher or IPC bridge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
import math
import subprocess
import threading
import time

from .connection_proof import stop_process


class LaunchState(StrEnum):
    NEW = "new"
    STARTING_GATEWAY = "starting_gateway"
    GATEWAY_READY = "gateway_ready"
    STARTING_CLIENT = "starting_client"
    ACTIVE = "active"
    STOPPING = "stopping"
    CLEANUP_BLOCKED = "cleanup_blocked"
    CLOSED = "closed"


class LaunchLifecycleError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ChildCleanup:
    role: str
    exit_code: int | None
    reaped: bool
    forced: bool | None
    code: str | None = None


@dataclass(frozen=True)
class LaunchCleanup:
    confirmed: bool
    runtime_confirmed: bool
    children: tuple[ChildCleanup, ...]

    @property
    def forced(self):
        return any(child.forced for child in self.children)


class LaunchOwner:
    """Serialize blocking methods on the launch worker; request_cancel is thread-safe.

    Only child handles created here are stopped. A ready notification must come
    from a verified future handshake, not elapsed startup time or an open port.
    """

    def __init__(
        self, *, startup_timeout=120.0, clock=time.monotonic, runtime_cleanup=None
    ):
        if (
            type(startup_timeout) not in (int, float)
            or not math.isfinite(startup_timeout)
            or startup_timeout <= 0
        ):
            raise LaunchLifecycleError("INVALID_STARTUP_TIMEOUT")
        if runtime_cleanup is not None and not callable(runtime_cleanup):
            raise LaunchLifecycleError("INVALID_RUNTIME_CLEANUP_SOURCE")
        self._state = LaunchState.NEW
        self._children = {}
        self._forced = set()
        self._cancel = threading.Event()
        self._lock = threading.RLock()
        self._report = None
        self._clock = clock
        self._startup_timeout = startup_timeout
        self._deadline = None
        self._runtime_cleanup = runtime_cleanup

    def __enter__(self):
        with self._lock:
            self._require(LaunchState.NEW)
        return self

    def __exit__(self, exc_type, exc, traceback):
        report = self.close()
        if not report.confirmed:
            if exc is None:
                raise LaunchLifecycleError("LAUNCH_CLEANUP_UNCONFIRMED")
            exc.add_note("LAUNCH_CLEANUP_UNCONFIRMED")
        return False

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def report(self):
        with self._lock:
            return self._report

    def request_cancel(self):
        self._cancel.set()

    def _require(self, expected):
        if self._state != expected:
            raise LaunchLifecycleError("INVALID_LAUNCH_TRANSITION")
        if self._cancel.is_set():
            self.close()
            raise LaunchLifecycleError("LAUNCH_CANCELLED")

    def _spawn(self, role, command, *, cwd, expected, starting):
        with self._lock:
            self._require(expected)
            if role == "client":
                self.check_health()
            if (
                not isinstance(command, (list, tuple))
                or not command
                or any(
                    not isinstance(part, str) or not part or "\x00" in part
                    for part in command
                )
            ):
                raise LaunchLifecycleError("INVALID_CHILD_COMMAND")
            self._state = starting
            self._deadline = self._clock() + self._startup_timeout
            try:
                process = subprocess.Popen(
                    tuple(command),
                    cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except (OSError, ValueError):
                self.close()
                raise LaunchLifecycleError("CHILD_START_FAILED") from None
            self._children[role] = process
            if self._cancel.is_set():
                self.close()
                raise LaunchLifecycleError("LAUNCH_CANCELLED")

    def start_gateway(self, command, *, cwd=None):
        self._spawn(
            "gateway",
            command,
            cwd=cwd,
            expected=LaunchState.NEW,
            starting=LaunchState.STARTING_GATEWAY,
        )

    def gateway_ready(self):
        with self._lock:
            self._require(LaunchState.STARTING_GATEWAY)
            self.check_health()
            self._state = LaunchState.GATEWAY_READY

    def start_client(self, command, *, cwd=None):
        self._spawn(
            "client",
            command,
            cwd=cwd,
            expected=LaunchState.GATEWAY_READY,
            starting=LaunchState.STARTING_CLIENT,
        )

    def client_ready(self):
        with self._lock:
            self._require(LaunchState.STARTING_CLIENT)
            self.check_health()
            self._state = LaunchState.ACTIVE

    def check_health(self):
        with self._lock:
            if self._state in (
                LaunchState.CLOSED,
                LaunchState.CLEANUP_BLOCKED,
                LaunchState.STOPPING,
            ):
                raise LaunchLifecycleError("INVALID_LAUNCH_TRANSITION")
            if self._cancel.is_set():
                self.close()
                raise LaunchLifecycleError("LAUNCH_CANCELLED")
            if (
                self._state
                in (LaunchState.STARTING_GATEWAY, LaunchState.STARTING_CLIENT)
                and self._clock() >= self._deadline
            ):
                self.close()
                raise LaunchLifecycleError("LAUNCH_STARTUP_TIMEOUT")
            try:
                exited = any(
                    process.poll() is not None for process in self._children.values()
                )
            except Exception:
                self.close()
                raise LaunchLifecycleError("OWNED_CHILD_STATUS_UNAVAILABLE") from None
            if exited:
                self.close()
                raise LaunchLifecycleError("OWNED_CHILD_EXITED")

    def close(self, *, runtime_cleanup=None):
        """Attempt every child in reverse order; require proof for engine descendants.

        runtime_cleanup is a trusted owner callback for future gateway/OS ownership
        evidence. Root-process exit alone must never imply that XMage also exited.
        """
        with self._lock:
            if self._state == LaunchState.CLOSED:
                return self._report
            self._state = LaunchState.STOPPING
            reports = []
            for role, process in reversed(tuple(self._children.items())):
                try:
                    result = stop_process(process)
                    if result.get("forced"):
                        self._forced.add(role)
                    reports.append(
                        ChildCleanup(
                            role,
                            result.get("exit_code"),
                            result.get("reaped") is True,
                            role in self._forced,
                        )
                    )
                except Exception:
                    # Keep trying the other owned handles. No raw exception,
                    # command line, path, token or deck data enters this report.
                    try:
                        exit_code = process.poll()
                    except Exception:
                        exit_code = None
                    reports.append(
                        ChildCleanup(
                            role,
                            exit_code,
                            False,
                            True if role in self._forced else None,
                            "CHILD_CLEANUP_UNCONFIRMED",
                        )
                    )
            runtime_confirmed = "gateway" not in self._children
            runtime_cleanup = (
                runtime_cleanup
                if runtime_cleanup is not None
                else self._runtime_cleanup
            )
            if not runtime_confirmed and runtime_cleanup is not None:
                try:
                    runtime_confirmed = runtime_cleanup() is True
                except Exception:
                    runtime_confirmed = False
            confirmed = runtime_confirmed and all(child.reaped for child in reports)
            self._report = LaunchCleanup(confirmed, runtime_confirmed, tuple(reports))
            self._state = (
                LaunchState.CLOSED if confirmed else LaunchState.CLEANUP_BLOCKED
            )
            return self._report
