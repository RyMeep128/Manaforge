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
from mtg_play import connection_proof as transport  # noqa: E402
from mtg_play.launch_lifecycle import LaunchOwner  # noqa: E402
from mtg_play.viewer_bootstrap import export_viewer_bootstrap  # noqa: E402
from play_native_metadata import provision_metadata  # noqa: E402


def main():
    artifacts = ROOT / "Mtg_Projects/mtg_play_unity/Artifacts"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--post-resolution-pass",
        action="store_true",
        help="Confirm one more native pass with a guarded phase transition; requires --observe-resolution",
    )
    parser.add_argument(
        "--observe-resolution",
        action="store_true",
        help="After the pass, require the exact source on the battlefield and show a read-only snapshot; requires --continue-priority",
    )
    parser.add_argument(
        "--continue-priority",
        action="store_true",
        help="After the confirmed ability, submit one real priority pass on the same session; requires --native-metadata",
    )
    parser.add_argument(
        "--native-metadata",
        action="store_true",
        help="Require guarded native source/instance evidence; requires --creature-ability or --finish-attacks",
    )
    parser.add_argument(
        "--artwork",
        action="store_true",
        help="Require the exact public fixture printings from Core's existing offline image cache",
    )
    parser.add_argument(
        "--arena-backdrop",
        action="store_true",
        help="Use the locally prepared Arena tutorial battlefield with --artwork",
    )
    parser.add_argument(
        "--arena-buttons",
        action="store_true",
        help="Require the locally prepared Arena opening button textures with --artwork",
    )
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument(
        "--finish-attacks",
        action="store_true",
        help="Show one native attacker-selection finish choice after diagnostic setup; requires --native-metadata",
    )
    scenario.add_argument(
        "--creature-ability",
        action="store_true",
        help="Submit one native casting-ability choice from Unity; diagnostic setup and stack observation",
    )
    scenario.add_argument(
        "--priority-pass",
        action="store_true",
        help="Submit one explicit engine priority pass from Unity",
    )
    scenario.add_argument(
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
    if args.native_metadata and not (args.creature_ability or args.finish_attacks):
        parser.error(
            "--native-metadata requires --creature-ability or --finish-attacks"
        )
    if args.finish_attacks and not args.native_metadata:
        parser.error("--finish-attacks requires --native-metadata")
    if args.finish_attacks and args.continue_priority:
        parser.error("--finish-attacks is an isolated combat choice")
    if args.continue_priority and not args.native_metadata:
        parser.error("--continue-priority requires --native-metadata")
    if args.observe_resolution and not args.continue_priority:
        parser.error("--observe-resolution requires --continue-priority")
    if args.post_resolution_pass and not args.observe_resolution:
        parser.error("--post-resolution-pass requires --observe-resolution")
    if args.artwork and (
        args.first_land
        or args.priority_pass
        or args.creature_ability
        or args.finish_attacks
    ):
        parser.error(
            "--artwork uses the modern Forest/Ornithopter opening-only fixture"
        )
    if args.arena_buttons and not args.artwork:
        parser.error("--arena-buttons requires --artwork")
    if args.arena_backdrop and not args.artwork:
        parser.error("--arena-backdrop requires --artwork")
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
    artwork_directory = artwork_pin = None
    if args.artwork:
        sys.path.insert(0, str(ROOT / "Mtg_Projects/mtg_core"))
        from mtg_core.services import CardService
        from mtg_play.artwork_bundle import export_artwork_bundle

        def offline(*unused, **keywords):
            raise RuntimeError("LIVE_ARTWORK_NETWORK_FORBIDDEN")

        service = CardService(
            fetch_json_fn=offline, fetch_bytes_fn=offline, fetch_bulk_fn=offline
        )
        printings = [
            service.get_print(set_code=code, collector_number=number)
            for code, number in (("m21", "272"), ("m15", "223"))
        ]
        if any(not card for card in printings):
            parser.error(
                "Exact public fixture printings are missing from the installed Core catalog"
            )
        artwork_directory = str(output / "artwork")
        manifest, artwork_pin = export_artwork_bundle(
            service,
            [card["id"] for card in printings],
            artwork_directory,
            session_id="live-opening",
            viewer_id="human",
        )
        if len(manifest["entries"]) != 2 or manifest["unavailable"]:
            parser.error(
                "Cache both exact public fixture images through Core before using --artwork"
            )
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
        metadata_context = workspace / "metadata-context.json"

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
                        *(
                            ["-Dmanaforge.finishAttacks=true"]
                            if args.finish_attacks
                            else []
                        ),
                        *(
                            ["-Dmanaforge.postResolutionPass=true"]
                            if args.post_resolution_pass
                            else []
                        ),
                        *(
                            ["-Dmanaforge.observeResolution=true"]
                            if args.observe_resolution
                            else []
                        ),
                        *(
                            ["-Dmanaforge.continuePriority=true"]
                            if args.continue_priority
                            else []
                        ),
                        *(
                            ["-Dmanaforge.metadataContext=" + str(metadata_context)]
                            if args.native_metadata
                            else []
                        ),
                        *(["-Dmanaforge.artworkOpening=true"] if args.artwork else []),
                        "-cp",
                        str(server.parent / "classes")
                        + os.pathsep
                        + str(server / "lib/*"),
                        "ManaforgeLiveOpening",
                        str(port),
                        hashpin,
                        str(output / "gateway-ready.json"),
                        *(
                            ["--first-land"]
                            if args.first_land or args.priority_pass
                            else []
                        ),
                        *(
                            ["--first-creature"]
                            if args.creature_ability or args.finish_attacks
                            else []
                        ),
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
                if args.native_metadata:
                    provision_metadata(
                        gateway, server_process, server, metadata_context, hashpin
                    )
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
                if args.priority_pass:
                    command += ["-manaforgeLivePriority", "1"]
                if args.creature_ability:
                    command += ["-manaforgeLiveCreature", "1"]
                if args.finish_attacks:
                    command += ["-manaforgeLiveFinishAttacks", "1"]
                if args.continue_priority:
                    command += ["-manaforgeLiveContinuePriority", "1"]
                if args.observe_resolution:
                    command += ["-manaforgeLiveObserveResolution", "1"]
                if args.post_resolution_pass:
                    command += ["-manaforgeLivePostResolutionPass", "1"]
                if not args.interactive:
                    command += [
                        "-batchmode",
                        "-manaforgeLiveScript",
                        "1",
                        "-manaforgeLiveCapture",
                        "1",
                    ]
                if args.arena_backdrop:
                    command += ["-manaforgeArenaBackdrop", "1"]
                owner.start_preview(
                    command,
                    preview_bootstrap=export_viewer_bootstrap(
                        port=address["port"],
                        session_id="live-opening",
                        viewer_id="human",
                        engine_version="1.4.62-V1",
                        artifact_manifest_sha256=hashpin,
                        viewer_key=key,
                        artwork_directory=artwork_directory,
                        artwork_manifest_sha256=artwork_pin,
                    ),
                )
                ready = wait_file("ready", 30)
                if (
                    ready.get("live_opening") is not True
                    or ready.get("snapshot_count") != 1
                    or ready.get("ack_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_READY_FAILED")
                if args.arena_backdrop and (
                    ready.get("arena_backdrop") is not True
                    or ready.get("arena_backdrop_resource")
                    != "LocalCardVisuals/Playmats/ArenaTutorialBattlefield"
                ):
                    raise RuntimeError("LIVE_UNITY_BACKDROP_NOT_PRESENTED")
                if (
                    not (
                        args.first_land
                        or args.priority_pass
                        or args.creature_ability
                        or args.finish_attacks
                    )
                    and ready.get("mulligan_controls") is not True
                ):
                    raise RuntimeError("LIVE_UNITY_MULLIGAN_CONTROLS_NOT_PRESENTED")
                if args.arena_buttons and (
                    ready.get("arena_button_skins") is not True
                    or ready.get("arena_button_glows") != 2
                ):
                    raise RuntimeError("LIVE_UNITY_BUTTON_SKINS_NOT_PRESENTED")
                owner.client_ready()
                if args.artwork and ready.get("artwork_count") != 7:
                    raise RuntimeError("LIVE_UNITY_ARTWORK_NOT_PRESENTED")
                if args.interactive:
                    print(
                        "Select Finish attacks within 60 seconds; no attackers have been selected in this public fixture."
                        if args.finish_attacks
                        else "Select the casting ability, then Pass priority in each of the next two prompts; 60 seconds per choice."
                        if args.post_resolution_pass
                        else "Select the casting ability, then Pass priority when the next decision appears; 60 seconds per choice."
                        if args.continue_priority
                        else "Live casting ability ready: select the engine-offered ability within 60 seconds."
                        if args.creature_ability
                        else "Live priority ready: select Pass priority within 60 seconds."
                        if args.priority_pass
                        else "Live land ready: select Play land within 60 seconds."
                        if args.first_land
                        else "Live opening ready: inspect cards, then choose Yes or No within 60 seconds. The spike closes after submission.",
                        flush=True,
                    )
                if args.continue_priority:
                    followup = wait_file("priority-ready", 60)
                    if (
                        followup.get("snapshot_count") != 2
                        or followup.get("followup_priority_presented") is not True
                    ):
                        raise RuntimeError("LIVE_UNITY_FOLLOWUP_NOT_PRESENTED")
                if args.observe_resolution:
                    observed = wait_file("battlefield-ready", 60)
                    if (
                        observed.get("snapshot_count") != 3
                        or observed.get("battlefield_observation_presented") is not True
                        or observed.get("confirmed_receipt_count") != 2
                    ):
                        raise RuntimeError("LIVE_UNITY_BATTLEFIELD_NOT_PRESENTED")
                if args.post_resolution_pass:
                    phase = wait_file("phase-ready", 60)
                    if (
                        phase.get("snapshot_count") != 4
                        or phase.get("phase_transition_presented") is not True
                    ):
                        raise RuntimeError("LIVE_UNITY_PHASE_NOT_PRESENTED")
                chosen = wait_file("choice", 60)
                if (
                    chosen.get("ack_count")
                    != (
                        6
                        if args.post_resolution_pass
                        else 4
                        if args.continue_priority
                        else 2
                    )
                    or chosen.get("viewer_cleared") is not True
                ):
                    raise RuntimeError("LIVE_UNITY_CHOICE_FAILED")
                if args.post_resolution_pass and (
                    observed.get("post_resolution_priority_presented") is not True
                    or chosen.get("confirmed_receipt_count") != 3
                    or chosen.get("uncertain_receipt_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_POST_RESOLUTION_RECEIPT_FAILED")
                if args.finish_attacks and (
                    ready.get("attack_finish_presented") is not True
                    or chosen.get("confirmed_receipt_count") != 1
                    or chosen.get("uncertain_receipt_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_ATTACK_FINISH_RECEIPT_FAILED")
                # The scene quits after clearing. Observe its owned handle rather than health-checking an expected exit.
                client = owner._children["client"]
                client.wait(timeout=15)
                closed = json.loads(
                    (output / "closed.json").read_text(encoding="utf-8-sig")
                )
                if client.returncode != 0 or closed.get("viewer_cleared") is not True:
                    raise RuntimeError("LIVE_UNITY_CLEAR_FAILED")
                if args.artwork and closed.get("artwork_count") != 0:
                    raise RuntimeError("LIVE_UNITY_ARTWORK_NOT_CLEARED")
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
                if (
                    args.native_metadata
                    and native.get("unity_post_resolution_priority_confirmed")
                    is not args.post_resolution_pass
                ):
                    raise RuntimeError("LIVE_UNITY_POST_PHASE_CONFIRMATION_FAILED")
                if (
                    args.native_metadata
                    and native.get("unity_post_resolution_priority_submitted")
                    is not args.post_resolution_pass
                ):
                    raise RuntimeError("LIVE_UNITY_POST_RESOLUTION_EVIDENCE_FAILED")
                if (
                    args.native_metadata
                    and native.get("unity_followup_priority_confirmed")
                    is not args.observe_resolution
                ):
                    raise RuntimeError("LIVE_UNITY_PRIORITY_CONFIRMATION_FAILED")
                if (
                    args.native_metadata
                    and native.get("unity_battlefield_transition_observed")
                    is not args.observe_resolution
                ):
                    raise RuntimeError("LIVE_UNITY_BATTLEFIELD_EVIDENCE_FAILED")
                if (
                    args.native_metadata
                    and native.get("unity_followup_priority_submitted")
                    is not args.continue_priority
                ):
                    raise RuntimeError("LIVE_UNITY_FOLLOWUP_EVIDENCE_FAILED")
                if args.native_metadata and any(
                    native.get(field) is not True
                    for field in (
                        "native_stack_source_matched",
                        "native_cast_instance_matched",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_CAST_INSTANCE_UNPROVEN")
                if (
                    args.native_metadata
                    and native.get("unity_casting_ability_confirmed")
                    is not args.creature_ability
                ):
                    raise RuntimeError("LIVE_UNITY_ABILITY_CONFIRMATION_FAILED")
                if args.finish_attacks and any(
                    native.get(field) is not True
                    for field in (
                        "native_attack_source_offered",
                        "native_empty_attack_submitted",
                        "native_combat_advanced",
                        "unity_attack_finish_submitted",
                        "unity_attack_finish_confirmed",
                        "creature_resolved",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_EVIDENCE_FAILED")
                if args.creature_ability and any(
                    native.get(field) is not True
                    for field in (
                        "creature_spell_on_stack",
                        "unity_casting_ability_submitted",
                        "native_cast_ability_matched",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_CREATURE_EVIDENCE_FAILED")
                if (
                    args.creature_ability
                    and native.get("creature_resolved") is not False
                ):
                    raise RuntimeError("LIVE_UNITY_CREATURE_RESOLUTION_UNPROVEN")
                if args.priority_pass and (
                    native.get("unity_priority_pass_submitted") is not True
                    or native.get("first_land_observed") is not False
                ):
                    raise RuntimeError("LIVE_UNITY_PRIORITY_EVIDENCE_FAILED")
                if (args.first_land or args.priority_pass) and native.get(
                    "priority_pass_submitted"
                ) is not True:
                    raise RuntimeError("LIVE_UNITY_PRIORITY_NOT_SUBMITTED")
                evidence = dict(
                    live_engine=True,
                    unity_connected=True,
                    authenticated_choice=True,
                    engine_advanced=True,
                    viewer_cleared=True,
                    public_fixture_only=True,
                    first_land_observed=args.first_land,
                    priority_pass_submitted=args.first_land or args.priority_pass,
                    unity_priority_pass_submitted=args.priority_pass,
                    unity_casting_ability_submitted=args.creature_ability,
                    native_cast_ability_matched=args.creature_ability
                    or args.finish_attacks,
                    creature_spell_on_stack=args.creature_ability
                    or args.finish_attacks,
                    creature_resolved=args.finish_attacks,
                    mulligan_controls=ready.get("mulligan_controls", False),
                    arena_button_glows=ready.get("arena_button_glows", 0),
                    arena_button_skins=ready.get("arena_button_skins", False),
                    arena_backdrop_resource=ready.get("arena_backdrop_resource"),
                    arena_backdrop=args.arena_backdrop,
                    artwork_presented=args.artwork,
                    artwork_card_count=ready.get("artwork_count", 0),
                )
                if args.native_metadata:
                    evidence.update(
                        native_stack_source_matched=True,
                        native_cast_instance_matched=True,
                        unity_casting_ability_confirmed=args.creature_ability,
                        unity_followup_priority_submitted=args.continue_priority,
                        unity_battlefield_transition_observed=args.observe_resolution,
                        unity_followup_priority_confirmed=args.observe_resolution,
                        unity_post_resolution_priority_submitted=args.post_resolution_pass,
                        unity_post_resolution_priority_confirmed=args.post_resolution_pass,
                    )
                if args.continue_priority:
                    evidence.update(followup_priority_presented=True, snapshot_count=2)
                if args.finish_attacks:
                    evidence.update(
                        native_attack_source_offered=True,
                        native_empty_attack_submitted=True,
                        native_combat_advanced=True,
                        unity_attack_finish_submitted=True,
                        unity_attack_finish_confirmed=True,
                        attack_finish_presented=True,
                        confirmed_receipt_count=1,
                        uncertain_receipt_count=0,
                    )
                if args.observe_resolution:
                    evidence.update(
                        battlefield_observation_presented=True, snapshot_count=3
                    )
                if args.post_resolution_pass:
                    evidence.update(
                        post_resolution_priority_presented=True,
                        phase_transition_presented=True,
                        snapshot_count=4,
                        confirmed_receipt_count=3,
                        uncertain_receipt_count=0,
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
        "Packaged Unity confirmed explicit Finish attacks using native selection/priority evidence; viewer cleared and roots reaped."
        if args.finish_attacks
        else "Packaged Unity confirmed three commands on one session and displayed the next native phase; viewer cleared and roots reaped."
        if args.post_resolution_pass
        else "Packaged Unity confirmed the exact ability and priority pass, observed the spell source on the battlefield, cleared the viewer and reaped owned roots."
        if args.observe_resolution
        else "Packaged Unity casting ability confirmed, then next priority passed on the same session; pass outcome uncertain, viewer cleared and roots reaped."
        if args.continue_priority
        else "Packaged Unity casting ability submitted to XMage; Memnite stack entry observed, viewer cleared and roots reaped. Resolution remains in the separate Java proof."
        if args.creature_ability
        else "Packaged Unity priority pass submitted to XMage; engine advanced, viewer cleared and roots reaped. No full game claimed."
        if args.priority_pass
        else "Packaged Unity -> authenticated Java -> XMage first land passed; engine zone change observed, viewer cleared and roots reaped. No full game claimed."
        if args.first_land
        else "Packaged Unity -> authenticated Java -> XMage opening choice passed; viewer cleared and roots reaped. No full game claimed."
    )
    print(str(output))


if __name__ == "__main__":
    main()
