"""Pinned-engine Java-owned human/AI opening proof; no Python game actions or Unity."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
from mtg_play import connection_proof as transport  # noqa: E402
from play_native_metadata import provision_metadata  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument(
        "--first-creature",
        action="store_true",
        help="Java-owned zero-cost creature cast, stack observation and native resolution",
    )
    scenario.add_argument(
        "--first-land",
        action="store_true",
        help="All-Forest engine-backed land action probe; no Unity changes",
    )
    parser.add_argument("--xmage-root", type=Path, default=transport.DEFAULT_BUNDLE)
    parser.add_argument("--jdk-path", type=Path, default=transport.DEFAULT_JDK)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "Mtg_Projects/mtg_play_unity/Artifacts/LiveOpening/report.json",
    )
    parser.add_argument(
        "--native-metadata",
        action="store_true",
        help="Provision a private Java metadata channel once at startup; requires --first-creature",
    )
    args = parser.parse_args()
    if args.native_metadata and not args.first_creature:
        parser.error("--native-metadata requires --first-creature")
    output = args.output.resolve()
    artifacts = (ROOT / "Mtg_Projects/mtg_play_unity/Artifacts").resolve()
    if not output.is_relative_to(artifacts) or output == artifacts:
        parser.error("Use a report path under Unity Artifacts")
    output.unlink(missing_ok=True)
    expected = dict(
        live_engine=True,
        java_game_commands=True,
        human_ai_seats=True,
        opening_hand_count=7,
        decision_received=True,
        unity_connected=False,
        public_projection_validated=True,
        public_choice_submitted=True,
        engine_advanced=True,
        duplicate_native_submission_prevented=True,
        authenticated_choice=True,
        duplicate_receipt_reused=True,
        disconnect_uncertainty_retained=True,
    )
    if args.first_land:
        expected["first_land_observed"] = True
        expected["priority_pass_submitted"] = True
        expected["unity_priority_pass_submitted"] = False
    if args.first_creature:
        expected["creature_spell_on_stack"] = True
        expected["creature_resolved"] = True
        expected["unity_casting_ability_submitted"] = False
        expected["native_cast_ability_matched"] = True
    if args.native_metadata:
        expected["native_stack_source_matched"] = True
        expected["native_cast_instance_matched"] = True
    evidence = None

    def consume(first, events, launch, port, server_process, server):
        nonlocal evidence
        java = args.xmage_root.resolve() / "java/jre1.8.0_201/bin/java.exe"
        classes = server.parent / "classes"
        workspace = server.parent / "java-live-opening"
        workspace.mkdir()
        diagnostic = (workspace / "bridge.log").open("wb")
        metadata_context = workspace / "metadata-context.json"
        manifest_hash = hashlib.sha256(
            (transport.HERE / "artifacts.json").read_bytes()
        ).hexdigest()
        process = subprocess.Popen(
            [
                str(java),
                "-Djava.awt.headless=true",
                "-Dfile.encoding=UTF-8",
                "-Djava.net.preferIPv4Stack=true",
                *(
                    ["-Dmanaforge.metadataContext=" + str(metadata_context)]
                    if args.native_metadata
                    else []
                ),
                "-cp",
                str(classes) + os.pathsep + str(server / "lib/*"),
                "ManaforgeLiveOpening",
                str(port),
                hashlib.sha256(
                    (transport.HERE / "artifacts.json").read_bytes()
                ).hexdigest(),
                *(["--first-land"] if args.first_land else []),
                *(["--first-creature"] if args.first_creature else []),
            ],
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=diagnostic,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            if args.native_metadata:
                provision_metadata(
                    process, server_process, server, metadata_context, manifest_hash
                )
            # Keep stdin open as the parent lifeline until the diagnostic finishes.
            process.wait(timeout=120)
            raw = process.stdout.read(4097)
            if process.returncode != 0 and len(raw) <= 4096:
                failed = json.loads(raw)
                stage = failed.get("stage")
                if stage in {
                    "initialize",
                    "connect",
                    "status",
                    "create_game",
                    "join_table",
                    "start_game",
                    "opening_decision",
                    "respond",
                }:
                    print("Java live opening failed at stage: " + stage, flush=True)
                if failed.get("code") in {
                    "LIVE_OPENING_UNSUPPORTED_PREGAME",
                    "LIVE_OPENING_TIMEOUT_OR_CANCELLED",
                    "LIVE_OPENING_ENGINE_FAILED",
                    "LIVE_OPENING_QUEUE_LIMIT",
                    "LIVE_OPENING_PIN",
                }:
                    print(failed["code"], flush=True)
                if failed.get("decision_family") in {
                    "GAME_ASK",
                    "GAME_CHOOSE_CHOICE",
                    "GAME_TARGET",
                    "GAME_SELECT",
                }:
                    print("Decision family: " + failed["decision_family"], flush=True)
            if (
                process.returncode != 0
                or len(raw) > 4096
                or json.loads(raw) != expected
            ):
                raise transport.ProofError("LIVE_JAVA_OPENING_FAILED")
            evidence = expected.copy()
        finally:
            cleanup = transport.stop_process(process)
            diagnostic.close()
            if cleanup.get("reaped") is not True or cleanup.get("forced"):
                raise transport.ProofError("LIVE_JAVA_OPENING_CLEANUP")

    result = transport.run_proof(
        args.xmage_root.resolve(), args.jdk_path.resolve(), runtime_consumer=consume
    )
    if not result["success"] or evidence is None:
        raise SystemExit(
            "LIVE_JAVA_OPENING_FAILED; inspect owned runtime compile/server diagnostics"
        )
    evidence.update(
        probe_version=2,
        public_fixture_only=True,
        roots_reaped=True,
        source_commit=subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(
        "Real XMage creature cast and resolved; stack cleared and 1/1 Memnite observed, duplicate receipts reused; cleanup passed. Unity casting remains pending."
        if args.first_creature
        else "Real XMage opening projected; authenticated boolean submitted once, duplicate receipt reused and engine advancement observed; cleanup passed. Unity integration remains pending."
    )


if __name__ == "__main__":
    main()
