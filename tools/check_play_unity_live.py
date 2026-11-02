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
    parser.add_argument(
        "--combat-keyword",
        choices=(
            "haste",
            "flying",
            "reach",
            "defender",
            "first-strike",
            "double-strike",
            "deathtouch",
            "lifelink",
            "trample",
            "menace",
            "vigilance",
            "indestructible",
            "planeswalker",
            "battle",
            "draw",
        ),
        help="Deterministic native core-combat scenario",
    )
    parser.add_argument(
        "--combat-trigger",
        action="store_true",
        help="Shield Sphere native block trigger, counter and damage scenario",
    )
    parser.add_argument(
        "--combat-spell",
        choices=("pump", "removal"),
        help="Dedicated Phyrexian combat spell/target/effect scenario",
    )
    parser.add_argument(
        "--human-blocking",
        action="store_true",
        help="Dedicated public Ornithopter versus Memnite human-blocking/damage scenario; conflicts with other scenarios",
    )
    parser.add_argument(
        "--complete-game",
        action="store_true",
        help="Continue core combat through natural native victory; requires --core-combat",
    )
    parser.add_argument(
        "--core-combat",
        action="store_true",
        help="Native multiple-attacker combat; requires --repeat-cycle, conflicts with --play-rounds",
    )
    parser.add_argument(
        "--play-rounds",
        type=int,
        choices=range(0, 7),
        default=0,
        help="Additional existing-creature combat/AI-turn rounds (0..6); requires --repeat-cycle",
    )
    parser.add_argument(
        "--repeat-cycle",
        action="store_true",
        help="Repeat combat after the next cast on the same session; requires --next-turn-cast",
    )
    parser.add_argument(
        "--next-turn-cast",
        action="store_true",
        help="Cast and resolve another creature on the same session; requires --loop-turn",
    )
    parser.add_argument(
        "--loop-turn",
        action="store_true",
        help="Continue to next human main phase; requires --complete-combat",
    )
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="Skip image capture; gameplay checks still run",
    )
    parser.add_argument(
        "--blocked-damage",
        action="store_true",
        help="One explicit pass and native blocker damage; requires --blocked-combat",
    )
    parser.add_argument(
        "--blocked-combat",
        action="store_true",
        help="Public AI blocker observation; requires --declared-priority and excludes --combat-damage",
    )
    parser.add_argument(
        "--complete-combat",
        action="store_true",
        help="One cleanup pass to postcombat main; requires --combat-damage",
    )
    parser.add_argument(
        "--combat-damage",
        action="store_true",
        help="One more explicit pass and native life change; requires --declared-priority",
    )
    parser.add_argument(
        "--declared-priority",
        action="store_true",
        help="One post-declaration priority pass; requires --finish-selected-attack",
    )
    parser.add_argument(
        "--finish-selected-attack",
        action="store_true",
        help="Finish the selected attack and observe native priority; requires --select-attacker",
    )
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--combat-priority",
        action="store_true",
        help="Confirm the next priority pass through a guarded phase transition; requires --finish-attacks",
    )
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
        "--select-attacker",
        action="store_true",
        help="Submit one explicit attacker choice; requires --native-metadata",
    )
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
    if args.combat_keyword:
        if (
            args.human_blocking
            or args.combat_trigger
            or args.combat_spell
            or args.core_combat
            or args.complete_game
            or args.select_attacker
            or args.finish_attacks
            or args.creature_ability
            or args.first_land
            or args.priority_pass
            or args.play_rounds
        ):
            parser.error("--combat-keyword is a separate scenario")
        args.native_metadata = True
        args.complete_game = args.combat_keyword == "draw"
    expected_outcome = (
        "draw"
        if args.combat_keyword == "draw"
        else "loss"
        if args.human_blocking
        else "win"
    )
    if args.combat_trigger:
        args.human_blocking = True
        if args.combat_spell or args.complete_game:
            parser.error("--combat-trigger is a separate blocking scenario")
    if args.human_blocking or args.combat_spell:
        args.native_metadata = True
    if args.combat_spell and (
        args.human_blocking
        or args.core_combat
        or args.complete_game
        or args.select_attacker
        or args.finish_attacks
        or args.creature_ability
        or args.first_land
        or args.priority_pass
        or args.play_rounds
    ):
        parser.error("--combat-spell is a separate scenario")
    if args.human_blocking and (
        args.core_combat
        or args.select_attacker
        or args.finish_attacks
        or args.creature_ability
        or args.first_land
        or args.priority_pass
        or args.play_rounds
    ):
        parser.error("--human-blocking is a separate scenario")
    if args.complete_game and not (
        args.core_combat or args.human_blocking or args.combat_keyword == "draw"
    ):
        parser.error("--complete-game requires --core-combat")
    if args.core_combat and (not args.repeat_cycle or args.play_rounds):
        parser.error("--core-combat requires --repeat-cycle and no --play-rounds")
    if args.play_rounds and not args.repeat_cycle:
        parser.error("--play-rounds requires --repeat-cycle")
    if args.repeat_cycle and not args.next_turn_cast:
        parser.error("--repeat-cycle requires --next-turn-cast")
    if args.next_turn_cast and not args.loop_turn:
        parser.error("--next-turn-cast requires --loop-turn")
    if args.loop_turn and not args.complete_combat:
        parser.error("--loop-turn requires --complete-combat")
    if args.blocked_damage and not args.blocked_combat:
        parser.error("--blocked-damage requires --blocked-combat")
    if args.blocked_combat and (not args.declared_priority or args.combat_damage):
        parser.error(
            "--blocked-combat requires --declared-priority and excludes --combat-damage"
        )
    if args.complete_combat and not args.combat_damage:
        parser.error("--complete-combat requires --combat-damage")
    if args.combat_damage and not args.declared_priority:
        parser.error("--combat-damage requires --declared-priority")
    if args.declared_priority and not args.finish_selected_attack:
        parser.error("--declared-priority requires --finish-selected-attack")
    if args.finish_selected_attack and not args.select_attacker:
        parser.error("--finish-selected-attack requires --select-attacker")
    if args.native_metadata and not (
        args.creature_ability
        or args.finish_attacks
        or args.select_attacker
        or args.human_blocking
        or args.combat_spell
        or args.combat_keyword
    ):
        parser.error(
            "--native-metadata requires --creature-ability, --finish-attacks or --select-attacker"
        )
    if (args.finish_attacks or args.select_attacker) and not args.native_metadata:
        parser.error("combat choices require --native-metadata")
    if args.combat_priority and not args.finish_attacks:
        parser.error("--combat-priority requires --finish-attacks")
    if (args.finish_attacks or args.select_attacker) and args.continue_priority:
        parser.error("combat choices cannot use --continue-priority")
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
        or args.select_attacker
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

        if args.combat_keyword:
            request_id = str(uuid.uuid4())
            server_process.stdin.write(
                json.dumps(
                    dict(
                        request_id=request_id,
                        command="prepare_combat_fixture",
                        skip_shuffling=True,
                    )
                )
                + "\n"
            )
            server_process.stdin.flush()
            prepared = server / "manaforge-responses" / (request_id + ".json")
            deadline = time.monotonic() + 10
            while not prepared.is_file():
                if server_process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("COMBAT_FIXTURE_SETUP_FAILED")
                time.sleep(0.02)
            if json.loads(prepared.read_text()) != {"ordered_decks": True}:
                raise RuntimeError("COMBAT_FIXTURE_SETUP_FAILED")
        with (workspace / "bridge.log").open("wb") as diagnostic:
            try:
                gateway = subprocess.Popen(
                    [
                        str(java),
                        "-Djava.awt.headless=true",
                        "-Dfile.encoding=UTF-8",
                        "-Djava.net.preferIPv4Stack=true",
                        f"-Dmanaforge.playRounds={args.play_rounds}",
                        f"-Dmanaforge.coreCombat={str(args.core_combat or args.human_blocking or bool(args.combat_spell) or bool(args.combat_keyword)).lower()}",
                        f"-Dmanaforge.coreFromOpening={str(args.human_blocking or bool(args.combat_spell) or bool(args.combat_keyword)).lower()}",
                        f"-Dmanaforge.combatSpell={args.combat_spell or ''}",
                        f"-Dmanaforge.combatTrigger={str(args.combat_trigger).lower()}",
                        f"-Dmanaforge.combatKeyword={args.combat_keyword or ''}",
                        f"-Dmanaforge.completeGame={str(args.complete_game).lower()}",
                        *(
                            ["-Dmanaforge.repeatCycle=true"]
                            if args.repeat_cycle
                            else []
                        ),
                        *(
                            ["-Dmanaforge.nextTurnCast=true"]
                            if args.next_turn_cast
                            else []
                        ),
                        *(["-Dmanaforge.loopTurn=true"] if args.loop_turn else []),
                        *(
                            ["-Dmanaforge.blockedDamage=true"]
                            if args.blocked_damage
                            else []
                        ),
                        *(
                            ["-Dmanaforge.blockedCombat=true"]
                            if args.blocked_combat
                            else []
                        ),
                        *(
                            ["-Dmanaforge.completeCombat=true"]
                            if args.complete_combat
                            else []
                        ),
                        *(
                            ["-Dmanaforge.combatDamage=true"]
                            if args.combat_damage
                            else []
                        ),
                        *(
                            ["-Dmanaforge.declaredPriority=true"]
                            if args.declared_priority
                            else []
                        ),
                        *(
                            ["-Dmanaforge.finishSelectedAttack=true"]
                            if args.finish_selected_attack
                            else []
                        ),
                        *(
                            ["-Dmanaforge.selectAttacker=true"]
                            if args.select_attacker
                            else []
                        ),
                        *(
                            ["-Dmanaforge.combatPriority=true"]
                            if args.combat_priority
                            else []
                        ),
                        *(
                            ["-Dmanaforge.finishAttacks=true"]
                            if args.finish_attacks or args.select_attacker
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
                            if args.creature_ability
                            or args.finish_attacks
                            or args.select_attacker
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
                if args.combat_keyword:
                    command += ["-manaforgeLiveCombatKeyword", args.combat_keyword]
                command += [
                    "-manaforgeLiveCombatTrigger",
                    "1" if args.combat_trigger else "0",
                ]
                if args.combat_spell:
                    command += ["-manaforgeLiveCombatSpell", args.combat_spell]
                command += [
                    "-manaforgeLiveHumanBlocking",
                    "1" if args.human_blocking else "0",
                ]
                command += [
                    "-manaforgeLiveCompleteGame",
                    "1" if args.complete_game else "0",
                ]
                command += [
                    "-manaforgeLiveCoreCombat",
                    "1" if args.core_combat else "0",
                ]
                command += ["-manaforgeLivePlayRounds", str(args.play_rounds)]
                if args.repeat_cycle:
                    command += ["-manaforgeLiveRepeatCycle", "1"]
                if args.next_turn_cast:
                    command += ["-manaforgeLiveNextTurnCast", "1"]
                if args.loop_turn:
                    command += ["-manaforgeLiveLoopTurn", "1"]
                if args.blocked_damage:
                    command += ["-manaforgeLiveBlockedDamage", "1"]
                if args.blocked_combat:
                    command += ["-manaforgeLiveBlockedCombat", "1"]
                if args.complete_combat:
                    command += ["-manaforgeLiveCompleteCombat", "1"]
                if args.combat_damage:
                    command += ["-manaforgeLiveCombatDamage", "1"]
                if args.declared_priority:
                    command += ["-manaforgeLiveDeclaredPriority", "1"]
                if args.finish_selected_attack:
                    command += ["-manaforgeLiveFinishSelectedAttack", "1"]
                if args.select_attacker:
                    command += ["-manaforgeLiveSelectAttacker", "1"]
                if args.finish_attacks:
                    command += ["-manaforgeLiveFinishAttacks", "1"]
                if args.combat_priority:
                    command += ["-manaforgeLiveCombatPriority", "1"]
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
                        "0" if args.no_capture else "1",
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
                        or args.select_attacker
                    )
                    and not args.human_blocking
                    and not args.combat_spell
                    and not args.combat_keyword
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
                        "Follow the offered attacker, finish, priority and cleanup-discard responses through the next human main phase; the session is bounded to six minutes."
                        if args.loop_turn
                        else "Select the attacker, Finish attacks, then Pass priority three times; 60 seconds per choice."
                        if args.complete_combat
                        else "Select the attacker, Finish attacks, then Pass priority twice; 60 seconds per choice."
                        if args.combat_damage
                        else "Select the attacker, Finish attacks, then Pass priority; 60 seconds per choice."
                        if args.declared_priority
                        else "Select the attacker, then Finish attacks; 60 seconds per choice."
                        if args.finish_selected_attack
                        else "Select the offered attacker within 60 seconds; declaration remains open."
                        if args.select_attacker
                        else "Select Finish attacks, then the offered Pass priority; 60 seconds per choice."
                        if args.combat_priority
                        else "Select Finish attacks within 60 seconds; no attackers have been selected in this public fixture."
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
                if args.finish_attacks:
                    combat_result = wait_file("combat-result-ready", 60)
                    if (
                        combat_result.get("snapshot_count") != 2
                        or combat_result.get("post_combat_priority_presented")
                        is not True
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_RESULT_NOT_PRESENTED")
                if args.combat_priority:
                    combat_phase = wait_file("combat-priority-ready", 60)
                    if (
                        combat_phase.get("snapshot_count") != 3
                        or combat_phase.get("combat_priority_result_presented")
                        is not True
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_PHASE_NOT_PRESENTED")
                if args.select_attacker:
                    assignment = wait_file("attack-assignment-ready", 60)
                    if (
                        assignment.get("attack_assignment_presented") is not True
                        or assignment.get("snapshot_count") != 2
                    ):
                        raise RuntimeError("LIVE_UNITY_ATTACK_ASSIGNMENT_NOT_PRESENTED")
                if args.finish_selected_attack:
                    declaration = wait_file("declared-attack-ready", 60)
                    if (
                        declaration.get("declared_attack_presented") is not True
                        or declaration.get("snapshot_count") != 3
                    ):
                        raise RuntimeError("LIVE_UNITY_DECLARATION_NOT_PRESENTED")
                if args.declared_priority:
                    priority_result = wait_file("post-declared-priority-ready", 60)
                    if (
                        priority_result.get("snapshot_count") != 4
                        or priority_result.get("post_declared_priority_presented")
                        is not True
                    ):
                        raise RuntimeError(
                            "LIVE_UNITY_POST_DECLARED_PRIORITY_NOT_PRESENTED"
                        )
                if args.combat_damage:
                    damage = wait_file("combat-damage-ready", 60)
                    life_before = damage.get("defender_life_before")
                    life_after = damage.get("defender_life_after")
                    if (
                        damage.get("snapshot_count") != 5
                        or damage.get("combat_damage_presented") is not True
                        or type(life_before) is not int
                        or type(life_after) is not int
                        or life_before <= 1
                        or life_after != life_before - 1
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_DAMAGE_NOT_PRESENTED")
                if args.complete_combat:
                    cleanup_result = wait_file("combat-cleanup-ready", 60)
                    if (
                        cleanup_result.get("snapshot_count") != 6
                        or cleanup_result.get("combat_cleanup_presented") is not True
                        or cleanup_result.get("combat_group_count") != 0
                        or cleanup_result.get("postcombat_defender_life") != life_after
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_CLEANUP_NOT_PRESENTED")
                if args.blocked_damage:
                    blocked_damage = wait_file("blocked-damage-ready", 60)
                    if (
                        blocked_damage.get("snapshot_count") != 5
                        or blocked_damage.get("blocked_damage_presented") is not True
                        or blocked_damage.get("blocker_damage_before") != 0
                        or blocked_damage.get("blocker_damage_after") != 1
                        or type(blocked_damage.get("blocked_defender_life_before"))
                        is not int
                        or blocked_damage.get("blocked_defender_life_before")
                        != blocked_damage.get("blocked_defender_life_after")
                    ):
                        raise RuntimeError("LIVE_UNITY_BLOCKED_DAMAGE_NOT_PRESENTED")
                if args.loop_turn:
                    turn_result = wait_file("next-human-turn-ready", 300)
                    if (
                        turn_result.get("next_human_turn_presented") is not True
                        or turn_result.get("turn_number")
                        != turn_result.get("turn_loop_start", -10) + 2
                    ):
                        raise RuntimeError("LIVE_UNITY_NEXT_HUMAN_TURN_NOT_PRESENTED")
                if args.next_turn_cast:
                    cast_result = wait_file("next-turn-creature-ready", 180)
                    if (
                        cast_result.get("next_turn_creature_presented") is not True
                        or cast_result.get("snapshot_count")
                        != turn_result["snapshot_count"] + 3
                    ):
                        raise RuntimeError(
                            "LIVE_UNITY_NEXT_TURN_CREATURE_NOT_PRESENTED"
                        )
                if args.repeat_cycle:
                    repeated_result = wait_file("repeated-combat-ready", 240)
                    if (
                        repeated_result.get("repeated_combat_presented") is not True
                        or repeated_result.get("repeat_defender_life_after")
                        != repeated_result.get("repeat_defender_life_before", -10) - 1
                    ):
                        raise RuntimeError("LIVE_UNITY_REPEATED_COMBAT_NOT_PRESENTED")
                    returned_result = wait_file("repeated-turn-ready", 240)
                    if (
                        returned_result.get("repeated_turn_presented") is not True
                        or returned_result.get("turn_number")
                        != returned_result.get("turn_loop_start", -10) + 4
                        or returned_result.get("postcombat_defender_life")
                        != repeated_result.get("repeat_defender_life_after")
                    ):
                        raise RuntimeError("LIVE_UNITY_REPEATED_TURN_NOT_PRESENTED")
                if args.play_rounds:
                    rounds_result = wait_file("play-rounds-ready", 240)
                    if (
                        rounds_result.get("play_rounds_presented") is not True
                        or rounds_result.get("play_rounds") != args.play_rounds
                        or rounds_result.get("turn_number")
                        != returned_result["turn_number"] + 2 * args.play_rounds
                        or rounds_result.get("postcombat_defender_life")
                        != returned_result["postcombat_defender_life"]
                        - args.play_rounds
                    ):
                        raise RuntimeError("LIVE_UNITY_PLAY_ROUNDS_NOT_PRESENTED")
                if args.core_combat:
                    core_result = wait_file("core-combat-ready", 240)
                    if (
                        core_result.get("core_combat_presented") is not True
                        or core_result.get("core_life_after")
                        != core_result.get("core_life_before", -10) - 2
                    ):
                        raise RuntimeError("LIVE_UNITY_CORE_COMBAT_NOT_PRESENTED")
                if args.complete_game:
                    game_result = wait_file("game-ready", 240)
                    if (
                        game_result.get("game_presented") is not True
                        or game_result.get("native_game_outcome") != expected_outcome
                    ):
                        raise RuntimeError("LIVE_UNITY_GAME_RESULT_NOT_PRESENTED")
                if args.human_blocking:
                    block_result = wait_file("human-block-ready", 240)
                    if block_result.get("human_block_presented") is not True:
                        raise RuntimeError("LIVE_UNITY_HUMAN_BLOCK_NOT_PRESENTED")
                if args.combat_spell:
                    spell_result = wait_file("combat-spell-ready", 240)
                    if (
                        spell_result.get("combat_spell_presented") is not True
                        or spell_result.get(
                            "spell_buff_seen"
                            if args.combat_spell == "pump"
                            else "spell_death_seen"
                        )
                        is not True
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_SPELL_NOT_PRESENTED")
                if (
                    args.combat_trigger
                    and block_result.get("combat_trigger_presented") is not True
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_TRIGGER_NOT_PRESENTED")
                if args.combat_keyword:
                    case_result = wait_file("combat-case-ready", 240)
                    if (
                        case_result.get("combat_case_presented") is not True
                        or case_result.get("combat_case") != args.combat_keyword
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_CASE_NOT_PRESENTED")
                    if (
                        args.combat_keyword in ("planeswalker", "battle")
                        and case_result.get("permanent_defender_presented") is not True
                    ):
                        raise RuntimeError(
                            "LIVE_UNITY_PERMANENT_DEFENDER_NOT_PRESENTED"
                        )
                chosen = wait_file("choice", 60)
                if (
                    chosen.get("ack_count")
                    != (
                        2 * (chosen.get("snapshot_count", 0) - 1)
                        if args.loop_turn
                        or args.human_blocking
                        or args.combat_spell
                        or args.combat_keyword
                        else 10
                        if args.complete_combat
                        else 8
                        if args.combat_damage or args.blocked_damage
                        else 6
                        if args.declared_priority
                        else 4
                        if args.combat_priority or args.finish_selected_attack
                        else 6
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
                    or chosen.get("snapshot_count")
                    != (3 if args.combat_priority else 2)
                    or chosen.get("confirmed_receipt_count")
                    != (2 if args.combat_priority else 1)
                    or chosen.get("uncertain_receipt_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_ATTACK_FINISH_RECEIPT_FAILED")
                if (
                    args.combat_priority
                    and combat_result.get("combat_priority_action_presented")
                    is not True
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_PRIORITY_NOT_PRESENTED")
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
                if (
                    args.native_metadata
                    and not args.human_blocking
                    and not args.combat_spell
                    and not args.combat_keyword
                    and any(
                        native.get(field) is not True
                        for field in (
                            "native_stack_source_matched",
                            "native_cast_instance_matched",
                        )
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_CAST_INSTANCE_UNPROVEN")
                if (
                    args.native_metadata
                    and not args.human_blocking
                    and not args.combat_spell
                    and not args.combat_keyword
                    and native.get("unity_casting_ability_confirmed")
                    is not args.creature_ability
                ):
                    raise RuntimeError("LIVE_UNITY_ABILITY_CONFIRMATION_FAILED")
                if args.select_attacker:
                    if (
                        ready.get("attacker_choice_presented") is not True
                        or chosen.get("snapshot_count")
                        != (
                            game_result["snapshot_count"]
                            if args.complete_game
                            else core_result["snapshot_count"]
                            if args.core_combat
                            else rounds_result["snapshot_count"]
                            if args.play_rounds
                            else returned_result["snapshot_count"]
                            if args.repeat_cycle
                            else cast_result["snapshot_count"]
                            if args.next_turn_cast
                            else turn_result["snapshot_count"]
                            if args.loop_turn
                            else 6
                            if args.complete_combat
                            else 5
                            if args.combat_damage or args.blocked_damage
                            else 4
                            if args.declared_priority
                            else 3
                            if args.finish_selected_attack
                            else 2
                        )
                        or chosen.get("confirmed_receipt_count")
                        != (
                            chosen["snapshot_count"] - 1
                            if args.loop_turn
                            else 5
                            if args.complete_combat
                            else 4
                            if args.combat_damage or args.blocked_damage
                            else 3
                            if args.declared_priority
                            else 2
                            if args.finish_selected_attack
                            else 1
                        )
                        or chosen.get("uncertain_receipt_count") != 0
                    ):
                        raise RuntimeError("LIVE_UNITY_ATTACKER_RECEIPT_FAILED")
                    if (
                        any(
                            native.get(field) is not True
                            for field in (
                                "native_attack_source_offered",
                                "native_attacker_selected",
                                "native_attack_assignment_observed",
                                "creature_resolved",
                                "native_cast_ability_matched",
                                "creature_spell_on_stack",
                            )
                        )
                        or native.get("native_attack_selection_open")
                        is not (not args.finish_selected_attack)
                        or native.get("native_empty_attack_submitted") is not False
                    ):
                        raise RuntimeError("LIVE_UNITY_ATTACKER_EVIDENCE_FAILED")
                if args.loop_turn:
                    if (
                        any(
                            native.get(field) is not True
                            for field in (
                                "native_next_human_turn_observed",
                                "native_own_draw_observed",
                                "native_source_untapped",
                                "native_next_turn_actions_offered",
                            )
                        )
                        or type(native.get("native_cleanup_discard_observed"))
                        is not bool
                    ):
                        raise RuntimeError("LIVE_UNITY_TURN_LOOP_EVIDENCE_FAILED")
                if args.repeat_cycle and (
                    native.get("native_repeated_combat_observed") is not True
                    or native.get("native_repeated_turn_observed") is not True
                ):
                    raise RuntimeError("LIVE_UNITY_REPEATED_COMBAT_EVIDENCE_FAILED")
                if (
                    args.play_rounds
                    and native.get("native_play_rounds_completed") != args.play_rounds
                ):
                    raise RuntimeError("LIVE_UNITY_PLAY_ROUNDS_EVIDENCE_FAILED")
                if args.core_combat and (
                    native.get("native_core_combat_observed") is not True
                    or native.get("native_maximum_attackers") != 2
                ):
                    raise RuntimeError("LIVE_UNITY_CORE_COMBAT_EVIDENCE_FAILED")
                if (
                    args.complete_game
                    and native.get("native_game_outcome") != expected_outcome
                ):
                    raise RuntimeError("LIVE_UNITY_GAME_RESULT_UNPROVEN")
                if args.human_blocking and (
                    native.get("native_human_block_combat_observed") is not True
                    or chosen.get("confirmed_receipt_count")
                    != chosen.get("snapshot_count", 0) - 1
                    or chosen.get("uncertain_receipt_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_HUMAN_BLOCK_UNPROVEN")
                if args.combat_spell and (
                    native.get("native_combat_spell_effect_observed") is not True
                    or native.get("native_combat_spell_cycle_observed") is not True
                    or chosen.get("confirmed_receipt_count")
                    != chosen.get("snapshot_count", 0) - 1
                    or chosen.get("uncertain_receipt_count") != 0
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_SPELL_UNPROVEN")
                if (
                    args.combat_trigger
                    and native.get("native_combat_trigger_observed") is not True
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_TRIGGER_UNPROVEN")
                if args.combat_keyword:
                    if (
                        native.get("native_combat_case") != args.combat_keyword
                        or native.get("native_combat_case_completed") is not True
                        or native.get("native_combat_case_source_verified") is not True
                        or chosen.get("confirmed_receipt_count")
                        != chosen.get("snapshot_count", 0) - 1
                        or chosen.get("uncertain_receipt_count") != 0
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_CASE_UNPROVEN")
                    if (
                        args.combat_keyword != "draw"
                        and native.get("native_combat_case_damage_verified") is not True
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_DAMAGE_UNPROVEN")
                    if (
                        native.get("native_combat_case_amount_responses", 0) > 0
                        and case_result.get("case_numeric_submitted", 0) <= 0
                    ):
                        raise RuntimeError("LIVE_UNITY_COMBAT_ALLOCATION_NOT_SUBMITTED")
                if args.next_turn_cast and any(
                    native.get(field) is not True
                    for field in (
                        "unity_next_turn_cast_confirmed",
                        "unity_next_turn_ability_confirmed",
                        "unity_next_turn_resolution_confirmed",
                        "native_next_turn_creature_resolved",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_NEXT_CAST_EVIDENCE_FAILED")
                if args.declared_priority:
                    if (
                        any(
                            native.get(field) is not True
                            for field in (
                                "native_declared_priority_submitted",
                                "native_declared_priority_observed",
                            )
                        )
                        or type(native.get("native_blockers_observed")) is not bool
                        or native.get("native_blockers_observed")
                        is not priority_result.get("native_blockers_presented")
                    ):
                        raise RuntimeError(
                            "LIVE_UNITY_DECLARED_PRIORITY_EVIDENCE_FAILED"
                        )
                if args.blocked_combat:
                    if (
                        any(
                            native.get(field) is not True
                            for field in (
                                "native_blocking_fixture",
                                "native_blocker_projection_validated",
                                "native_blockers_observed",
                            )
                        )
                        or priority_result.get("native_blocker_names_presented")
                        is not True
                        or type(priority_result.get("native_blocker_count_presented"))
                        is not int
                        or priority_result["native_blocker_count_presented"] <= 0
                    ):
                        raise RuntimeError("LIVE_UNITY_BLOCKED_COMBAT_NOT_PRESENTED")
                if args.complete_combat and any(
                    native.get(field) is not True
                    for field in (
                        "native_postcombat_main_observed",
                        "native_combat_cleared",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_CLEANUP_EVIDENCE_FAILED")
                if args.combat_damage and any(
                    native.get(field) is not True
                    for field in (
                        "native_combat_damage_pass_submitted",
                        "native_combat_damage_life_change_observed",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_DAMAGE_EVIDENCE_FAILED")
                if args.finish_selected_attack and any(
                    native.get(field) is not True
                    for field in (
                        "native_selected_attack_finished",
                        "native_declared_attack_observed",
                    )
                ):
                    raise RuntimeError("LIVE_UNITY_DECLARATION_EVIDENCE_FAILED")
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
                if (
                    args.finish_attacks
                    and native.get("unity_combat_priority_submitted")
                    is not args.combat_priority
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_PRIORITY_EVIDENCE_FAILED")
                if (
                    args.finish_attacks
                    and native.get("unity_combat_priority_confirmed")
                    is not args.combat_priority
                ):
                    raise RuntimeError("LIVE_UNITY_COMBAT_PRIORITY_CONFIRMATION_FAILED")
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
                    or args.finish_attacks
                    or args.select_attacker,
                    creature_spell_on_stack=args.creature_ability
                    or args.finish_attacks
                    or args.select_attacker,
                    creature_resolved=args.finish_attacks or args.select_attacker,
                    mulligan_controls=ready.get("mulligan_controls", False),
                    arena_button_glows=ready.get("arena_button_glows", 0),
                    arena_button_skins=ready.get("arena_button_skins", False),
                    arena_backdrop_resource=ready.get("arena_backdrop_resource"),
                    arena_backdrop=args.arena_backdrop,
                    artwork_presented=args.artwork,
                    artwork_card_count=ready.get("artwork_count", 0),
                )
                if (
                    args.native_metadata
                    and not args.human_blocking
                    and not args.combat_spell
                ):
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
                if args.select_attacker:
                    evidence.update(
                        native_attacker_selected=True,
                        native_attack_assignment_observed=True,
                        native_attack_selection_open=not args.finish_selected_attack,
                        attacker_choice_presented=True,
                        attack_assignment_presented=True,
                        snapshot_count=chosen["snapshot_count"]
                        if args.loop_turn
                        else 6
                        if args.complete_combat
                        else 5
                        if args.combat_damage or args.blocked_damage
                        else 4
                        if args.declared_priority
                        else 3
                        if args.finish_selected_attack
                        else 2,
                        confirmed_receipt_count=chosen["confirmed_receipt_count"]
                        if args.loop_turn
                        else 5
                        if args.complete_combat
                        else 4
                        if args.combat_damage or args.blocked_damage
                        else 3
                        if args.declared_priority
                        else 2
                        if args.finish_selected_attack
                        else 1,
                        uncertain_receipt_count=0,
                    )
                if args.combat_keyword:
                    evidence.update(
                        {
                            key: value
                            for key, value in native.items()
                            if key.startswith("native_combat_case")
                        }
                    )
                    evidence.update(
                        combat_case_presented=True,
                        snapshot_count=chosen["snapshot_count"],
                        confirmed_receipt_count=chosen["confirmed_receipt_count"],
                        uncertain_receipt_count=0,
                    )
                if args.combat_trigger:
                    evidence.update(
                        native_combat_trigger_observed=True,
                        combat_trigger_presented=True,
                    )
                if args.combat_spell:
                    evidence.update(
                        native_combat_spell_effect_observed=True,
                        native_combat_spell_cycle_observed=True,
                        combat_spell_presented=True,
                        combat_spell=args.combat_spell,
                        snapshot_count=chosen["snapshot_count"],
                        confirmed_receipt_count=chosen["confirmed_receipt_count"],
                        uncertain_receipt_count=0,
                    )
                if args.human_blocking:
                    evidence.update(
                        native_human_block_combat_observed=True,
                        human_block_presented=True,
                        snapshot_count=chosen["snapshot_count"],
                        confirmed_receipt_count=chosen["confirmed_receipt_count"],
                        uncertain_receipt_count=0,
                    )
                if args.complete_game:
                    evidence.update(
                        native_game_outcome=expected_outcome,
                        game_presented=True,
                    )
                if args.core_combat:
                    evidence.update(
                        native_core_combat_observed=True,
                        native_maximum_attackers=2,
                        core_combat_presented=True,
                    )
                if args.play_rounds:
                    evidence.update(
                        native_play_rounds_completed=args.play_rounds,
                        play_rounds_presented=True,
                        final_turn_number=rounds_result["turn_number"],
                        final_defender_life=rounds_result["postcombat_defender_life"],
                    )
                if args.repeat_cycle:
                    evidence.update(
                        native_repeated_combat_observed=True,
                        native_repeated_turn_observed=True,
                        repeated_turn_presented=True,
                        repeated_combat_presented=True,
                        repeat_defender_life_before=repeated_result[
                            "repeat_defender_life_before"
                        ],
                        repeat_defender_life_after=repeated_result[
                            "repeat_defender_life_after"
                        ],
                    )
                if args.next_turn_cast:
                    evidence.update(
                        unity_next_turn_cast_confirmed=True,
                        unity_next_turn_ability_confirmed=True,
                        unity_next_turn_resolution_confirmed=True,
                        native_next_turn_creature_resolved=True,
                        next_turn_creature_presented=True,
                    )
                if args.loop_turn:
                    evidence.update(
                        native_next_human_turn_observed=True,
                        native_own_draw_observed=True,
                        native_source_untapped=True,
                        native_next_turn_actions_offered=True,
                        native_cleanup_discard_observed=native[
                            "native_cleanup_discard_observed"
                        ],
                        next_human_turn_presented=True,
                    )
                if args.blocked_damage:
                    evidence.update(
                        native_blocked_damage_pass_submitted=True,
                        native_blocker_damage_observed=True,
                        blocked_damage_presented=True,
                        blocker_damage_before=blocked_damage["blocker_damage_before"],
                        blocker_damage_after=blocked_damage["blocker_damage_after"],
                        blocked_defender_life=blocked_damage[
                            "blocked_defender_life_after"
                        ],
                    )
                if args.blocked_combat:
                    evidence.update(
                        native_blocking_fixture=True,
                        native_blocker_projection_validated=True,
                        native_blocker_names_presented=True,
                        native_blocker_count_presented=priority_result[
                            "native_blocker_count_presented"
                        ],
                    )
                if args.complete_combat:
                    evidence.update(
                        native_postcombat_main_observed=True,
                        native_combat_cleared=True,
                        combat_cleanup_presented=True,
                        postcombat_defender_life=cleanup_result[
                            "postcombat_defender_life"
                        ],
                    )
                if args.combat_damage:
                    evidence.update(
                        native_combat_damage_pass_submitted=True,
                        native_combat_damage_life_change_observed=True,
                        combat_damage_presented=True,
                        defender_life_before=life_before,
                        defender_life_after=life_after,
                    )
                if args.declared_priority:
                    evidence.update(
                        native_declared_priority_submitted=True,
                        native_declared_priority_observed=True,
                        native_blockers_observed=native["native_blockers_observed"],
                        post_declared_priority_presented=True,
                    )
                if args.finish_selected_attack:
                    evidence.update(
                        native_selected_attack_finished=True,
                        native_declared_attack_observed=True,
                        declared_attack_presented=True,
                    )
                if args.finish_attacks:
                    evidence.update(
                        native_attack_source_offered=True,
                        native_empty_attack_submitted=True,
                        native_combat_advanced=True,
                        unity_attack_finish_submitted=True,
                        unity_attack_finish_confirmed=True,
                        attack_finish_presented=True,
                        confirmed_receipt_count=2 if args.combat_priority else 1,
                        uncertain_receipt_count=0,
                        post_combat_priority_presented=True,
                        snapshot_count=3 if args.combat_priority else 2,
                        unity_combat_priority_submitted=args.combat_priority,
                        unity_combat_priority_confirmed=args.combat_priority,
                        combat_priority_result_presented=args.combat_priority,
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
        f"Packaged Unity verified the native {args.combat_keyword} combat scenario, confirmed every input and cleared the viewer."
        if args.combat_keyword
        else "Packaged Unity blocked with Shield Sphere, resolved its native combat trigger and displayed the resulting counter and damage."
        if args.combat_trigger
        else f"Packaged Unity resolved the native combat {args.combat_spell} spell, confirmed the target effect and cleared the viewer."
        if args.combat_spell
        else "Packaged Unity cast a blocker, blocked a native AI attack, observed native blocked damage and cleared the viewer."
        if args.human_blocking
        else "Packaged Unity completed a natural combat victory, presented the authoritative native result, confirmed inputs and reaped owned processes."
        if args.complete_game
        else "Packaged Unity selected multiple native attackers, completed damage and cleanup, confirmed inputs and cleared the viewer."
        if args.core_combat
        else f"Packaged Unity completed {args.play_rounds} additional combat/AI-turn rounds using the second creature, confirmed every input, cleared the viewer and reaped owned roots."
        if args.play_rounds
        else "Packaged Unity repeated casting and combat on one session, confirmed the second life decrease and following human turn, cleared the viewer and reaped owned roots."
        if args.repeat_cycle
        else "Packaged Unity continued the turn loop, cast another creature, selected its ability and confirmed resolution on the same session; viewer cleared and roots reaped."
        if args.next_turn_cast
        else "Packaged Unity continued cleanup, the AI turn and the next human main phase on one session; turn inputs confirmed, viewer cleared and owned roots reaped."
        if args.loop_turn
        else "Packaged Unity confirmed four inputs and displayed one native damage marked on Ornithopter with unchanged life totals; viewer cleared and owned roots reaped."
        if args.blocked_damage
        else "Packaged Unity displayed engine-declared AI blocker names after three confirmed inputs; viewer cleared and owned roots reaped."
        if args.blocked_combat
        else "Packaged Unity confirmed five combat inputs, observed postcombat main with cleared combat and preserved life totals; viewer cleared and owned roots reaped."
        if args.complete_combat
        else "Packaged Unity confirmed four combat inputs and displayed the native combat-damage life change; viewer cleared and owned roots reaped."
        if args.combat_damage
        else "Packaged Unity confirmed attacker selection, Finish attacks and one priority pass; displayed the next native combat state, cleared the viewer and reaped owned roots."
        if args.declared_priority
        else "Packaged Unity confirmed attacker selection and Finish attacks, displayed native priority with the same assignment, cleared the viewer and reaped owned roots."
        if args.finish_selected_attack
        else "Packaged Unity submitted an attacker choice; Java verified the native assignment. Choice confirmed, declaration open; viewer cleared and roots reaped."
        if args.select_attacker
        else "Packaged Unity confirmed Finish attacks and the next priority pass, displayed the next native state read-only, cleared the viewer and reaped owned roots."
        if args.combat_priority
        else "Packaged Unity confirmed Finish attacks and displayed the next native priority state read-only; viewer cleared and roots reaped."
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
