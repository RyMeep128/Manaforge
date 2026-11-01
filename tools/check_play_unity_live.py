"""Opt-in packaged Unity -> authenticated Java -> real XMage opening. Public decks only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
from mtg_play import connection_proof as transport
from mtg_play.launch_lifecycle import LaunchOwner
from mtg_play.viewer_bootstrap import export_viewer_bootstrap


def main():
    artifacts = ROOT / "Mtg_Projects/mtg_play_unity/Artifacts"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--first-land",
        action="store_true",
        help="Show one real land offer after diagnostic pregame/keep; not a full match",
    )
    parser.add_argument("--xmage-root", type=Path, default=transport.DEFAULT_BUNDLE)
    parser.add_argument("--jdk-path", type=Path, default=transport.DEFAULT_JDK)
    parser.add_argument(
        "--output",
        type=Path,
        default=artifacts / ("UnityLive-" + uuid.uuid4().hex[:10]),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if (
        not output.is_relative_to(artifacts.resolve())
        or output == artifacts.resolve()
        or output.exists()
    ):
        parser.error("Choose a new directory under Unity Artifacts")
    player = ROOT / "Mtg_Projects/mtg_play_unity/Builds/Windows/ManaforgePlay.exe"
    if not player.is_file():
        parser.error("Build the current Unity player first")
    output.mkdir()
    hashpin = hashlib.sha256(
        (transport.HERE / "artifacts.json").read_bytes()
    ).hexdigest()
    evidence = None

    def consume(first, events, launch, port, server_process, server):
        nonlocal evidence
        owner = LaunchOwner(
            startup_timeout=120
        )  # Unity only; runtime is separately owned below.
        key = bytearray(secrets.token_bytes(32))
        gateway = None
        java = args.xmage_root.resolve() / "java/jre1.8.0_201/bin/java.exe"
        workspace = server.parent / "unity-live-opening"
        workspace.mkdir()

        def wait_file(name, seconds=90):
            deadline = time.monotonic() + seconds
            path = output / (name + ".json")
            while not path.is_file():
                if (
                    (output / "failed.json").is_file()
                    or time.monotonic() > deadline
                    or (gateway is not None and gateway.poll() is not None)
                ):
                    raise RuntimeError("LIVE_UNITY_REPORT_FAILED")
                if owner.state.value != "new":
                    owner.check_health()
                time.sleep(0.02)
            return json.loads(path.read_text(encoding="utf-8-sig"))

        with (workspace / "bridge.log").open("wb") as diagnostic:
            try:
                gateway = subprocess.Popen(
                    [
                        str(java),
                        "-Djava.awt.headless=true",
                        "-Dfile.encoding=UTF-8",
                        "-Djava.net.preferIPv4Stack=true",
                        "-cp",
                        str(server.parent / "classes")
                        + os.pathsep
                        + str(server / "lib/*"),
                        "ManaforgeLiveOpening",
                        str(port),
                        hashpin,
                        str(output / "gateway-ready.json"),
                        *(["--first-land"] if args.first_land else []),
                    ],
                    cwd=workspace,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=diagnostic,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                # One small private frame into our new empty owned pipe; no secrets on disk/argv.
                bootstrap = json.dumps(
                    dict(live_opening_bootstrap_version=1, viewer_key_hex=key.hex())
                ).encode()
                gateway.stdin.write(len(bootstrap).to_bytes(4, "big") + bootstrap)
                gateway.stdin.flush()
                address = wait_file("gateway-ready")
                if (
                    set(address) != {"host", "port"}
                    or address["host"] != "127.0.0.1"
                    or type(address["port"]) is not int
                    or not 1 <= address["port"] <= 65535
                ):
                    raise RuntimeError("LIVE_UNITY_ADDRESS_FAILED")
                command = [
                    str(player),
                    "-screen-fullscreen",
                    "0",
                    "-screen-width",
                    "1280",
                    "-screen-height",
                    "720",
                    "-logFile",
                    str(output / "player.log"),
                    "-manaforgeLiveOpening",
                    str(output),
                ]
                if args.first_land:
                    command += ["-manaforgeLiveLand", "1"]
                if not args.interactive:
                    command += [
                        "-batchmode",
                        "-manaforgeLiveScript",
                        "1",
                        "-manaforgeLiveCapture",
                        "1",
                    ]
                owner.start_preview(
                    command,
                    preview_bootstrap=export_viewer_bootstrap(
                        port=address["port"],
                        session_id="live-opening",
                        viewer_id="human",
                        engine_version="1.4.62-V1",
                        artifact_manifest_sha256=hashpin,
                        viewer_key=key,
                    ),
                )
                ready = wait_file("ready", 30)
                if (
                    ready.get("live_opening") is not True
                    or ready.get("snapshot_count") != 1
                    or ready.get("ack_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_READY_FAILED")
                owner.client_ready()
                if args.interactive:
                    print(
                        "Live land ready: select Play land within 60 seconds."
                        if args.first_land
                        else "Live opening ready: inspect cards, then choose Yes or No within 60 seconds. The spike closes after submission.",
                        flush=True,
                    )
                chosen = wait_file("choice", 60)
                if (
                    chosen.get("ack_count") != 2
                    or chosen.get("viewer_cleared") is not True
                ):
                    raise RuntimeError("LIVE_UNITY_CHOICE_FAILED")
                # The scene quits after clearing. Observe its owned handle rather than health-checking an expected exit.
                client = owner._children["client"]
                client.wait(timeout=15)
                closed = json.loads(
                    (output / "closed.json").read_text(encoding="utf-8-sig")
                )
                if client.returncode != 0 or closed.get("viewer_cleared") is not True:
                    raise RuntimeError("LIVE_UNITY_CLEAR_FAILED")
                gateway.stdin.close()
                gateway.wait(timeout=15)
                raw = gateway.stdout.read(4097)
                if gateway.returncode != 0 or len(raw) > 4096:
                    raise RuntimeError("LIVE_UNITY_GATEWAY_FAILED")
                native = json.loads(raw)
                for field in (
                    "unity_connected",
                    "authenticated_choice",
                    "engine_advanced",
                    "public_projection_validated",
                    "public_choice_submitted",
                ):
                    if native.get(field) is not True:
                        raise RuntimeError("LIVE_UNITY_EVIDENCE_FAILED")
                if args.first_land and native.get("first_land_observed") is not True:
                    raise RuntimeError("LIVE_UNITY_LAND_NOT_OBSERVED")
                evidence = dict(
                    live_engine=True,
                    unity_connected=True,
                    authenticated_choice=True,
                    engine_advanced=True,
                    viewer_cleared=True,
                    public_fixture_only=True,
                    first_land_observed=args.first_land,
                )
            finally:
                key[:] = bytes(len(key))
                cleanup = owner.close()
                stopped = transport.stop_process(gateway)
                if (
                    not cleanup.confirmed
                    or cleanup.forced
                    or (
                        gateway is not None
                        and (not stopped.get("reaped") or stopped.get("forced"))
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_CLEANUP_FAILED")

    result = transport.run_proof(
        args.xmage_root.resolve(), args.jdk_path.resolve(), runtime_consumer=consume
    )
    if not result["success"] or evidence is None:
        raise SystemExit("LIVE_UNITY_FAILED; inspect owned runtime/player diagnostics")
    evidence.update(
        probe_version=1,
        source_commit=subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
    )
    (output / "report.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Packaged Unity -> authenticated Java -> XMage first land passed; engine zone change observed, viewer cleared and roots reaped. No full game claimed."
        if args.first_land
        else "Packaged Unity -> authenticated Java -> XMage opening choice passed; viewer cleared and roots reaped. No full game claimed."
    )
    print(str(output))


if __name__ == "__main__":
    main()
