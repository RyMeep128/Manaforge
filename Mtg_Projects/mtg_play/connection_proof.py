"""Standalone XMage connection experiment. No Qt or Manaforge application imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
DEFAULT_BUNDLE = HERE / "mage-full_1.4.62-dev_2026-10-03_20-47"
DEFAULT_JDK = Path(r"C:\Program Files\Java\jdk-23")
START_TIMEOUT = 120
CONNECT_TIMEOUT = 30
STOP_TIMEOUT = 10
EVENTS = {
    "connection",
    "disconnected",
    "message",
    "error",
    "transport_connected",
    "callback",
    "connected",
    "status",
    "shutdown",
    "table_created",
    "joined",
    "started",
    "game_started",
    "game_state",
    "decision",
    "response_sent",
    "game_over",
    "game_result",
    "concede_sent",
}


class ProofError(RuntimeError):
    """An actionable feasibility failure with an optional stable timeout code."""

    def __init__(self, message, *, code=None):
        self.code = code
        super().__init__(message)


def decode_event(line: str) -> dict:
    try:
        event = json.loads(line)
    except (ValueError, TypeError) as error:
        raise ProofError("Malformed bridge JSON") from error
    if (
        not isinstance(event, dict)
        or type(event.get("protocol")) is not int
        or event["protocol"] != 1
        or not isinstance(event.get("event"), str)
        or event.get("event") not in EVENTS
    ):
        raise ProofError("Invalid bridge protocol event")
    if event["event"] == "callback" and (
        not isinstance(event.get("method"), str)
        or type(event.get("message_id")) is not int
    ):
        raise ProofError("Callback lacks method/message_id")
    return event


class BridgeEvents:
    """Drain stdout continuously so callbacks cannot block the Java process."""

    def __init__(self, process: subprocess.Popen, transcript):
        self.process = process
        self.transcript = transcript
        self.events: queue.Queue = queue.Queue()
        self.callbacks: list[dict] = []
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    event = decode_event(line)
                    # Diagnostics retain routing metadata, never private views or prompts.
                    diagnostic = {
                        key: event[key]
                        for key in (
                            "protocol",
                            "event",
                            "request_id",
                            "method",
                            "message_id",
                        )
                        if key in event
                    }
                    self.transcript.write(json.dumps(diagnostic) + "\n")
                    self.transcript.flush()
                    self.events.put(event)
                except ProofError as error:
                    self.events.put(error)
        except (OSError, ValueError) as error:
            self.events.put(ProofError(f"Cannot read bridge output: {error}"))
        finally:
            self.events.put(None)

    def wait(self, event_name: str, deadline: float, request_id: str | None = None):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProofError(
                    f"Timed out waiting for bridge {event_name}",
                    code="ENGINE_OPERATION_TIMEOUT",
                )
            try:
                event = self.events.get(timeout=remaining)
            except queue.Empty as error:
                raise ProofError(
                    f"Timed out waiting for bridge {event_name}",
                    code="ENGINE_OPERATION_TIMEOUT",
                ) from error
            if event is None:
                raise ProofError(
                    f"Bridge exited unexpectedly while waiting for {event_name} "
                    f"(exit={self.process.poll()}); inspect bridge.log"
                )
            if isinstance(event, Exception):
                raise event
            if event["event"] == "error":
                raise ProofError(f"XMage bridge error: {event.get('message', event)}")
            if event["event"] == "callback":
                self.callbacks.append(event)
            if event["event"] == event_name and (
                request_id is None or event.get("request_id") == request_id
            ):
                return event


def send(process: subprocess.Popen, command: str, request_id: str, **fields):
    try:
        process.stdin.write(
            json.dumps(
                {
                    "protocol": 1,
                    "command": command,
                    "request_id": request_id,
                    **fields,
                }
            )
            + "\n"
        )
        process.stdin.flush()
    except (OSError, ValueError) as error:
        raise ProofError(f"Cannot send {command} to bridge: {error}") from error


def stop_process(process: subprocess.Popen | None, shutdown_line: str | None = None):
    """Reap only a process created by this runner; never kill by name or port."""
    if process is None:
        return {"started": False}
    forced = False
    if process.poll() is None:
        try:
            if shutdown_line is not None:
                process.stdin.write(shutdown_line + "\n")
                process.stdin.flush()
            else:
                process.stdin.close()  # EOF requests a graceful exit from either host.
            process.wait(timeout=STOP_TIMEOUT)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            if process.poll() is None:
                forced = True
                process.kill()
            process.wait(timeout=STOP_TIMEOUT)
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()
    return {
        "started": True,
        "pid": process.pid,
        "exit_code": process.returncode,
        "forced": forced,
        "reaped": process.poll() is not None,
    }


def reserve_port(port: int = 0) -> socket.socket:
    listener = socket.socket()
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
    except OSError as error:
        listener.close()
        raise ProofError(f"Local port {port} is unavailable: {error}") from error
    return listener


def validate_installation(bundle: Path, jdk: Path):
    java = bundle / "java/jre1.8.0_201/bin/java.exe"
    javac = jdk / "bin/javac.exe"
    for tool in (java, javac):
        if not tool.is_file():
            raise ProofError(f"Missing Java tool: {tool}; set --xmage-root/--jdk-path")
    manifest = json.loads((HERE / "artifacts.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["artifacts"].items():
        artifact = bundle / relative
        if not artifact.is_file():
            raise ProofError(f"Missing XMage artifact: {artifact}")
        with artifact.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != expected:
            raise ProofError(
                f"XMage artifact/version mismatch: {relative}; expected SHA-256 "
                f"{expected}, got {actual}. Use the pinned bundle; do not auto-repin."
            )
    return java, javac, manifest


def link_or_copy(source, destination):
    try:
        os.link(source, destination)
        return str(destination)
    except OSError:
        return shutil.copy2(source, destination)


def prepare_workspace(bundle: Path, workspace: Path, port: int, secondary: int):
    server = workspace / "server"
    original = bundle / "xmage/mage-server"
    for name in ("lib", "plugins"):
        shutil.copytree(original / name, server / name, copy_function=link_or_copy)
    shutil.copytree(original / "config", server / "config")
    shutil.copy2(original / "server.msg.txt", server / "server.msg.txt")
    config_path = server / "config/config.xml"
    tree = ET.parse(config_path)
    settings = tree.getroot().find("server")
    if settings is None:
        raise ProofError("XMage configuration has no server element")
    settings.set("serverAddress", "127.0.0.1")
    settings.set("port", str(port))
    settings.set("secondaryBindPort", str(secondary))
    settings.set("authenticationActivated", "false")
    tree.write(config_path, encoding="utf-8", xml_declaration=True)
    return server


def wait_for_server(process: subprocess.Popen, log: Path, deadline: float):
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProofError(
                f"XMage server exited ({process.returncode}); inspect {log}"
            )
        text = log.read_text(encoding="utf-8", errors="replace")
        if "Started MAGE server - listening on" in text:
            return
        if "Failed to start server" in text or "Unable to start MAGE server" in text:
            raise ProofError(f"XMage server startup failed; inspect {log}")
        time.sleep(0.1)
    raise ProofError(
        f"XMage server startup timed out; inspect {log}",
        code="ENGINE_OPERATION_TIMEOUT",
    )


def run_proof(
    bundle: Path,
    jdk: Path,
    port: int = 0,
    scenario=None,
    runtime_consumer=None,
    *,
    diagnostics=None,
) -> dict:
    if diagnostics is None:
        if __package__:
            from .diagnostics import LifecycleDiagnostics
        else:
            from diagnostics import LifecycleDiagnostics
        diagnostics = LifecycleDiagnostics()
    with diagnostics.stage("runtime_validation"):
        java, javac, manifest = validate_installation(bundle, jdk)
    workspace = (
        HERE / ".runtime" / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    )
    workspace.mkdir(parents=True)
    result = {
        "success": False,
        "workspace": str(workspace),
        "engine": manifest["engine"],
    }
    server_process = bridge_process = events = None
    logs = []
    peers = []
    reservations = []
    failure = None
    try:
        with diagnostics.stage("workspace_preparation"):
            reservations.append(reserve_port(port))
            reservations.append(reserve_port())
            port, secondary = [item.getsockname()[1] for item in reservations]
            server = prepare_workspace(bundle, workspace, port, secondary)
        with diagnostics.stage("bridge_compilation"):
            classes = workspace / "classes"
            classes.mkdir()
            classpath = str(server / "lib/*")
            compile_log = (workspace / "compile.log").open("w", encoding="utf-8")
            logs.append(compile_log)
            compiled = subprocess.run(
                [
                    str(javac),
                    "--release",
                    "8",
                    "-encoding",
                    "UTF-8",
                    "-cp",
                    classpath,
                    "-d",
                    str(classes),
                    *map(str, sorted((HERE / "java").glob("*.java"))),
                ],
                stdout=compile_log,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            if compiled.returncode:
                raise ProofError(
                    f"Java bridge compilation failed; inspect {compile_log.name}"
                )
        result.update({"primary_port": port, "secondary_port": secondary})
        classpath = os.pathsep.join((str(classes), classpath))
        server_log_path = workspace / "server.log"
        server_log = server_log_path.open("w", encoding="utf-8")
        bridge_log = (workspace / "bridge.log").open("w", encoding="utf-8")
        transcript = (workspace / "events.jsonl").open("w", encoding="utf-8")
        logs.extend((server_log, bridge_log, transcript))
        # Release just before startup. A competing bind still fails startup; never reuse it.
        for reservation in reservations:
            reservation.close()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        base = [
            str(java),
            "-Djava.awt.headless=true",
            "-Dfile.encoding=UTF-8",
            "-Djava.net.preferIPv4Stack=true",
            "-Dh2.bindAddress=127.0.0.1",
        ]
        with diagnostics.stage("server_startup"):
            server_process = subprocess.Popen(
                [*base, "-Xmx1024m", "-cp", classpath, "ManaforgeServerHost"],
                cwd=server,
                stdin=subprocess.PIPE,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                creationflags=flags,
            )
            print(f"Waiting for local XMage server; logs: {workspace}", flush=True)
            wait_for_server(
                server_process, server_log_path, time.monotonic() + START_TIMEOUT
            )
        with diagnostics.stage("client_connection"):
            bridge_dir = workspace / "bridge"
            bridge_dir.mkdir()
            bridge_process = subprocess.Popen(
                [*base, "-Xmx256m", "-cp", classpath, "ManaforgeBridge"],
                cwd=bridge_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=bridge_log,
                text=True,
                encoding="utf-8",
                creationflags=flags,
            )
            events = BridgeEvents(bridge_process, transcript)
            deadline = time.monotonic() + CONNECT_TIMEOUT
            send(
                bridge_process,
                "connect",
                "connect-1",
                port=port,
                username="mf_" + uuid.uuid4().hex[:10],
            )
            events.wait("connected", deadline, "connect-1")
        with diagnostics.stage("engine_handshake"):
            send(bridge_process, "status", "status-1")
            status = events.wait("status", deadline, "status-1")
            if (
                not status.get("connected")
                or status.get("engine_version") != manifest["engine"]
            ):
                raise ProofError(f"Unexpected engine status: {status}")
            if not events.callbacks:
                events.wait("callback", deadline)
            result.update({"status": status, "callbacks": list(events.callbacks)})
        if scenario is not None or runtime_consumer is not None:

            def launch_peer():
                peer_dir = workspace / ("peer-" + str(len(peers)))
                peer_dir.mkdir()
                peer_log = (peer_dir / "bridge.log").open("w", encoding="utf-8")
                peer_transcript = (peer_dir / "events.jsonl").open(
                    "w", encoding="utf-8"
                )
                logs.extend((peer_log, peer_transcript))
                peer = subprocess.Popen(
                    [*base, "-Xmx256m", "-cp", classpath, "ManaforgeBridge"],
                    cwd=peer_dir,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=peer_log,
                    text=True,
                    encoding="utf-8",
                    creationflags=flags,
                )
                peer_events = BridgeEvents(peer, peer_transcript)
                peers.append((peer, peer_events))
                return peer, peer_events

            if runtime_consumer is not None:
                runtime_consumer(
                    bridge_process, events, launch_peer, port, server_process, server
                )
            if scenario is not None:
                result["gameplay"] = scenario(bridge_process, events, launch_peer, port)
        with diagnostics.stage("runtime_shutdown"):
            send(bridge_process, "shutdown", "shutdown-1")
            shutdown = events.wait(
                "shutdown", time.monotonic() + STOP_TIMEOUT, "shutdown-1"
            )
            if shutdown.get("connected") is not False:
                raise ProofError("Bridge did not confirm disconnection")
            result["disconnected"] = True
    except (Exception, KeyboardInterrupt) as error:
        failure = str(error) or type(error).__name__
    finally:
        cleanup_stage = diagnostics.begin("process_cleanup")
        cleanup_errors = []
        for reservation in reservations:
            try:
                reservation.close()
            except OSError:
                cleanup_errors.append("Port reservation cleanup failed")
        # Continue cleanup even if one process cannot be reaped.
        for index, (peer, peer_events) in enumerate(peers):
            try:
                if peer.poll() is None:
                    send(peer, "shutdown", "peer-shutdown")
                    peer_events.wait(
                        "shutdown", time.monotonic() + STOP_TIMEOUT, "peer-shutdown"
                    )
                result["peer_" + str(index)] = stop_process(peer)
            except (ProofError, OSError, subprocess.SubprocessError) as error:
                cleanup_errors.append(f"peer {index}: {error}")
                try:
                    result["peer_" + str(index)] = stop_process(peer)
                except (OSError, subprocess.SubprocessError):
                    result["peer_" + str(index)] = {
                        "started": True,
                        "exit_code": None,
                        "reaped": False,
                    }
            peer_events.thread.join(timeout=2)
        for name, process, line in (
            ("bridge", bridge_process, None),
            ("server", server_process, "shutdown"),
        ):
            try:
                result[name] = stop_process(process, line)
            except (OSError, subprocess.SubprocessError) as error:
                cleanup_errors.append(f"{name}: {error}")
                # Missing cleanup data is not evidence that a started child exited.
                result[name] = {
                    "started": process is not None,
                    "exit_code": None,
                    "reaped": False,
                }
        if events is not None:
            events.thread.join(timeout=2)
        for log in logs:
            try:
                log.close()
            except OSError:
                cleanup_errors.append("Diagnostic stream cleanup failed")
        if cleanup_errors:
            failure = f"{failure or ''} Cleanup failed: {cleanup_errors}"
        if failure is None:
            for name in (
                "bridge",
                "server",
                *("peer_" + str(i) for i in range(len(peers))),
            ):
                state = result[name]
                if state.get("forced") or state.get("exit_code") != 0:
                    failure = f"{name} did not shut down normally: {state}"
        cleanup_failed = bool(cleanup_errors) or any(
            state.get("started") and (state.get("forced") or not state.get("reaped"))
            for name, state in result.items()
            if name in ("bridge", "server") or name.startswith("peer_")
        )
        diagnostics.end(cleanup_stage, failure="FAILED" if cleanup_failed else None)
        result["lifecycle"] = diagnostics.records
        result["success"] = failure is None
        if failure:
            result["error"] = failure
        try:
            (workspace / "result.json").write_text(
                json.dumps(result, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            # Do not discard process-exit evidence if diagnostic storage fails.
            result["diagnostics_write_failed"] = True
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xmage-root",
        type=Path,
        default=DEFAULT_BUNDLE,
        help="Bundle root containing xmage/ and java/",
    )
    parser.add_argument("--jdk-path", type=Path, default=DEFAULT_JDK)
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Primary loopback port (default: select an available port)",
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        result = run_proof(
            args.xmage_root.resolve(), args.jdk_path.resolve(), args.port
        )
    except (ProofError, OSError, subprocess.SubprocessError) as error:
        print(f"Connection proof failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
