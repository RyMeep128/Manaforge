"""Opt-in public Java/Unity session fixture; no XMage, user decks or gameplay commands."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))


def wait_file(owner, path, seconds=60):
    deadline = time.monotonic() + seconds
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("SESSION_FIXTURE_REPORT_TIMEOUT")
        owner.check_health()
        time.sleep(0.01)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate(value, code):
    if (
        set(value)
        != {
            "probe_version",
            "fixture_only",
            "code",
            "snapshot_count",
            "event_count",
            "viewer_cleared",
        }
        or value["probe_version"] != 1
        or value["fixture_only"] is not True
        or value["code"] != code
        or type(value["snapshot_count"]) is not int
        or type(value["event_count"]) is not int
        or value["snapshot_count"] != 2
        or value["event_count"] < 1
    ):
        raise RuntimeError("SESSION_FIXTURE_REPORT_INVALID")


def main():
    from mtg_play.launch_lifecycle import LaunchLifecycleError, LaunchOwner
    from mtg_play.viewer_bootstrap import export_viewer_bootstrap

    project = ROOT / "Mtg_Projects/mtg_play_unity"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "Artifacts" / ("SessionFixture-" + uuid.uuid4().hex[:12]),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open the fixture window for owner UI review; close it or press Ctrl+C to finish",
    )
    args = parser.parse_args()
    allowed = (project / "Artifacts").resolve()
    output = args.output.resolve()
    if output == allowed or not output.is_relative_to(allowed) or output.exists():
        parser.error("Choose a new directory under Unity Artifacts")
    player = project / "Builds/Windows/ManaforgePlay.exe"
    classes = project / "Artifacts/JavaDummy"
    jar = classes / "gson.jar"
    if (
        not player.is_file()
        or not (classes / "manaforge/protocol/DummyGateway.class").is_file()
        or not jar.is_file()
    ):
        parser.error("Run Unity EditMode preparation and Build first")
    output.mkdir(parents=True)
    protocol = ROOT / "Mtg_Projects/mtg_play/protocol/fixtures"
    fixture = json.loads(
        (protocol / "dummy-session-v1.json").read_text(encoding="utf-8")
    )
    public = copy.deepcopy(
        json.loads((protocol / "wire-receive-v1.json").read_text(encoding="utf-8"))[
            "positive"
        ][0]["envelope"]["body"]["snapshot"]["objects"][0]
    )
    public["characteristics"]["name"] = "Public fixture card"
    hidden = copy.deepcopy(fixture["snapshot"]["objects"][0])
    hidden["object_id"] = "fixture-hidden-object"
    fixture["snapshot"]["objects"] = [public, hidden]
    source = output / "public-snapshot.json"
    source.write_text(json.dumps(fixture), encoding="utf-8")
    # Dummy gateway has no engine descendants. This callback is never product evidence.
    owner = LaunchOwner(startup_timeout=90, runtime_cleanup=lambda: True)
    try:
        import os

        owner.start_gateway(
            [
                "java",
                "-cp",
                str(classes) + os.pathsep + str(jar),
                "manaforge.protocol.DummyGateway",
                str(source),
                "scene-fixture:" + str(output / "gateway-ready.json"),
            ]
        )
        key = bytes(
            range(32)
        )  # Public synthetic key, refused by production-facing fixture gate otherwise.
        boot = dict(
            viewer_key_hex=key.hex(),
            engine_version="fixture-engine",
            artifact_manifest_sha256="a" * 64,
            session_id="fixture-session",
            viewer_id="one",
            client_nonce="2" * 64,
            fixture_only=True,
        )
        encoded = json.dumps(boot).encode("utf-8")
        assert len(encoded) < 1024
        # One small public test frame into an empty owned pipe, not a product gateway bootstrap API.
        gateway = owner._children["gateway"]
        gateway.stdin.write(len(encoded).to_bytes(4, "big") + encoded)
        gateway.stdin.flush()
        address = wait_file(owner, output / "gateway-ready.json")
        if (
            set(address) != {"host", "port"}
            or address["host"] != "127.0.0.1"
            or type(address["port"]) is not int
            or not 1 <= address["port"] <= 65535
        ):
            raise RuntimeError("SESSION_FIXTURE_ADDRESS_INVALID")
        owner.gateway_ready()  # Fixture listener readiness; peer proof happens in Unity.
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
            "-manaforgeSessionFixture",
            str(output),
        ]
        if not args.interactive:
            command += ["-batchmode", "-manaforgeSessionCapture", "1"]
        owner.start_client(
            command,
            viewer_bootstrap=export_viewer_bootstrap(
                port=address["port"],
                session_id="fixture-session",
                viewer_id="one",
                engine_version="fixture-engine",
                artifact_manifest_sha256="a" * 64,
                viewer_key=key,
            ),
        )
        ready = wait_file(owner, output / "ready.json")
        validate(ready, "SESSION_FIXTURE_READY")
        owner.client_ready()  # Test-only artifact observation, not a product readiness handshake.
        if args.interactive:
            print(
                "Fixture ready. Inspect the public card and concealed back. Close the window or press Ctrl+C when finished.",
                flush=True,
            )
            try:
                while True:
                    owner.check_health()
                    time.sleep(0.1)
            except LaunchLifecycleError as error:
                if error.code != "OWNED_CHILD_EXITED":
                    raise
            except KeyboardInterrupt:
                pass
            print("Interactive fixture ended; no visual approval has been recorded.")
            return
        cleanup = owner.close()
        if (
            not cleanup.confirmed
            or cleanup.forced
            or {item.role: item.exit_code for item in cleanup.children}
            != dict(client=0, gateway=0)
        ):
            raise RuntimeError("SESSION_FIXTURE_CLEANUP_FAILED")
        closed = json.loads((output / "closed.json").read_text(encoding="utf-8-sig"))
        validate(closed, "SESSION_FIXTURE_OWNER_EOF")
        if closed["viewer_cleared"] is not True:
            raise RuntimeError("SESSION_FIXTURE_VIEWER_NOT_CLEARED")
        for image in ("connected.png", "cleared.png"):
            if not (output / image).is_file() or (output / image).stat().st_size < 1000:
                raise RuntimeError("SESSION_FIXTURE_CAPTURE_FAILED")
        log = (output / "player.log").read_text(encoding="utf-8-sig", errors="replace")
        if key.hex() in log or "viewer_key_hex" in log:
            raise RuntimeError("SESSION_FIXTURE_PRIVATE_LOG")
        assembly = player.parent / "ManaforgePlay_Data/Managed/Manaforge.Play.dll"
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        report = dict(
            report_version=1,
            fixture_only=True,
            passed=True,
            source_commit=commit,
            runtime_assembly_sha256=hashlib.sha256(assembly.read_bytes()).hexdigest(),
            ready=ready,
            closed=closed,
            roots_reaped=True,
            forced=False,
            descendant_containment_proven=False,
            human_ui_approved=False,
        )
        (output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "Packaged Java/Unity session fixture passed; viewer cleared and both roots exited without force."
        )
        print(f"Review captures and report: {output}")
    finally:
        if not owner.close().confirmed:
            raise RuntimeError("SESSION_FIXTURE_CLEANUP_UNCONFIRMED")


if __name__ == "__main__":
    main()
