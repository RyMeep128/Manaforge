"""Public native DeckDocument -> private owned Java launch-input probe. No engine/UI."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
from mtg_core.decks import Deck, DeckDocument, DeckEntry
from mtg_play.contracts import ADAPTER_VERSION, GameSetup, MatchSeat
from mtg_play.launch_manifest import export_launch_manifest
from mtg_play.launch_lifecycle import LaunchLifecycleError, LaunchOwner, LaunchState


def rejection_cases(payload):
    """Corrupt only public fixture bytes; expected pins remain independently trusted."""
    original = json.loads(payload)
    cases = [
        ("malformed_json", b"{"),
        ("invalid_utf8", b"\xff"),
        ("utf8_bom", b"\xef\xbb\xbf" + payload),
        ("duplicate_key", b'{"launch_manifest_version":1,' + payload[1:]),
    ]
    mutations = [
        ("engine_pin", lambda x: x["engine"].update(engine_version="wrong-engine")),
        ("adapter_pin", lambda x: x["engine"].update(adapter_version="wrong-adapter")),
        (
            "artifact_pin",
            lambda x: x["engine"].update(artifact_manifest_sha256="0" * 64),
        ),
        (
            "duplicate_seat",
            lambda x: x["seats"][1].update(seat_id=x["seats"][0]["seat_id"]),
        ),
        (
            "dangling_commander",
            lambda x: x["seats"][0]["document"]["deck"].update(
                commander_entry_ids=["missing-public-entry"]
            ),
        ),
    ]
    for name, mutate in mutations:
        value = json.loads(json.dumps(original))
        mutate(value)
        cases.append((name, json.dumps(value, separators=(",", ":")).encode("utf-8")))
    return cases


def check_rejection(command, payload, status):
    """Use the production launch owner, including its fail-closed child cleanup."""
    owner = LaunchOwner(startup_timeout=20, runtime_cleanup=lambda: True)
    observed = None
    try:
        owner.start_gateway(command, launch_manifest=payload)
        deadline = time.monotonic() + 10
        while True:
            owner.check_health()
            if time.monotonic() >= deadline:
                raise RuntimeError("PRIVATE_LAUNCH_REJECTION_TIMEOUT")
            time.sleep(0.01)
    except LaunchLifecycleError as failure:
        observed = failure.code
    finally:
        cleanup = owner.close()
    if (
        observed != "OWNED_CHILD_EXITED"
        or status.exists()
        or status.with_name(status.name + ".tmp").exists()
        or owner.client_bootstrap_written
        or owner.state != LaunchState.CLOSED
        or not cleanup.confirmed
        or cleanup.forced
        or [(x.role, x.exit_code) for x in cleanup.children] != [("gateway", 2)]
    ):
        raise RuntimeError("PRIVATE_LAUNCH_REJECTION_INVALID")
    try:
        owner.start_client(command)
    except LaunchLifecycleError as failure:
        if failure.code != "INVALID_LAUNCH_TRANSITION":
            raise RuntimeError("PRIVATE_LAUNCH_REJECTION_ADMISSION") from None
    else:
        raise RuntimeError("PRIVATE_LAUNCH_REJECTION_ADMISSION")


def main():
    artifacts = ROOT / "Mtg_Projects/mtg_play_unity/Artifacts"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classes", type=Path, default=artifacts / "JavaDummy")
    parser.add_argument(
        "--output", type=Path, default=artifacts / "GatewayLaunchProof/report.json"
    )
    args = parser.parse_args()
    classes = args.classes.resolve()
    output = args.output.resolve()
    if not classes.is_relative_to(artifacts.resolve()) or not output.is_relative_to(
        artifacts.resolve()
    ):
        parser.error("Use owned fixture paths under Unity Artifacts")
    # Never leave an earlier success report behind after a failed rerun.
    output.unlink(missing_ok=True)
    probe = classes / "manaforge/protocol/LaunchBootstrapProbe.class"
    gson = classes / "gson.jar"
    raw = (ROOT / "Mtg_Projects/mtg_play/artifacts.json").read_bytes()
    pins = json.loads(raw)
    if not probe.is_file() or not gson.is_file():
        parser.error("Compile the current protocol fixtures with --dummy-output first")
    if (
        hashlib.sha256(gson.read_bytes()).hexdigest()
        != pins["artifacts"]["xmage/mage-server/lib/gson-2.13.2.jar"]
    ):
        parser.error("Pinned Gson mismatch")
    runtime = shutil.which("java")
    if not runtime:
        parser.error("A Java runtime is required")
    deck = DeckDocument(
        deck=Deck(
            name="Public launch fixture",
            entries=[
                DeckEntry(
                    "public-entry",
                    "Public fixture card",
                    60,
                    card_id="fixture-printing",
                    oracle_id="fixture-oracle",
                )
            ],
        )
    )
    setup = GameSetup(
        (
            MatchSeat("human", "Public human", "local_human"),
            MatchSeat("opponent", "Public AI", "engine_ai"),
        ),
        format="freeform",
    )
    payload = export_launch_manifest(
        setup, {"human": deck, "opponent": deck}, manaforge_version="fixture-alpha.1"
    )
    owner = LaunchOwner(
        startup_timeout=20, runtime_cleanup=lambda: True
    )  # Diagnostic child has no engine descendants.
    with tempfile.TemporaryDirectory(
        prefix="manaforge-private-launch-proof-"
    ) as directory:
        status = Path(directory) / "validated.json"
        try:
            owner.start_gateway(
                [
                    runtime,
                    "-cp",
                    str(classes) + os.pathsep + str(gson),
                    "manaforge.protocol.LaunchBootstrapProbe",
                    str(status),
                    pins["engine"],
                    ADAPTER_VERSION,
                    hashlib.sha256(raw).hexdigest(),
                ],
                launch_manifest=payload,
            )
            deadline = time.monotonic() + 10
            while not status.is_file():
                owner.check_health()
                if time.monotonic() > deadline:
                    raise RuntimeError("PRIVATE_LAUNCH_PROBE_TIMEOUT")
                time.sleep(0.01)
            if (
                status.read_bytes() != b'{"validated":true}'
                or not owner.gateway_manifest_written
                or owner.client_bootstrap_written
                or owner.state != LaunchState.STARTING_GATEWAY
            ):
                raise RuntimeError("PRIVATE_LAUNCH_PROBE_INVALID")
        finally:
            cleanup = owner.close()
        if (
            not cleanup.confirmed
            or cleanup.forced
            or [(x.role, x.exit_code) for x in cleanup.children] != [("gateway", 0)]
        ):
            raise RuntimeError("PRIVATE_LAUNCH_PROBE_CLEANUP")
    rejected = []
    for name, invalid in rejection_cases(payload):
        with tempfile.TemporaryDirectory(
            prefix="manaforge-rejected-launch-proof-"
        ) as directory:
            status = Path(directory) / "validated.json"
            command = [
                runtime,
                "-cp",
                str(classes) + os.pathsep + str(gson),
                "manaforge.protocol.LaunchBootstrapProbe",
                str(status),
                pins["engine"],
                ADAPTER_VERSION,
                hashlib.sha256(raw).hexdigest(),
            ]
            check_rejection(command, invalid, status)
            rejected.append(name)
    output.parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    output.write_text(
        json.dumps(
            dict(
                probe_version=2,
                public_fixture_only=True,
                private_pipe_validated=True,
                rejected_cases=rejected,
                rejection_count=len(rejected),
                rejected_client_admission=True,
                engine_started=False,
                client_started=False,
                roots_reaped=True,
                forced=False,
                source_commit=commit,
                probe_class_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "Private native-deck launch input validated by owned Java receiver; EOF cleanup and nine fail-closed rejection cases passed. No engine or client started."
    )


if __name__ == "__main__":
    main()
