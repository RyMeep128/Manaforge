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
    parser.add_argument(
        "--loop-turn",
        action="store_true",
        help="Advance through cleanup and AI turn to next human main; requires --complete-combat",
    )
    parser.add_argument(
        "--blocked-damage",
        action="store_true",
        help="Native single-Ornithopter blocked damage observation; requires --blocked-combat",
    )
    parser.add_argument(
        "--blocked-combat",
        action="store_true",
        help="Public Ornithopter AI blocker fixture; requires --declared-priority and excludes --combat-damage",
    )
    parser.add_argument(
        "--complete-combat",
        action="store_true",
        help="One explicit pass to native postcombat main and cleared combat; requires --combat-damage",
    )
    parser.add_argument(
        "--combat-damage",
        action="store_true",
        help="One more explicit pass and native combat-damage life change; requires --declared-priority",
    )
    parser.add_argument(
        "--declared-priority",
        action="store_true",
        help="Submit one priority pass after declaration; requires --finish-selected-attack",
    )
    parser.add_argument(
        "--finish-selected-attack",
        action="store_true",
        help="Finish the selected single-attacker declaration; requires --select-attacker",
    )
    parser.add_argument(
        "--select-attacker",
        action="store_true",
        help="Select one native offered attacker and observe its engine assignment; requires --first-creature --native-metadata",
    )
    parser.add_argument(
        "--finish-attacks",
        action="store_true",
        help="Explicit public-fixture attack-selection finish proof; requires --first-creature --native-metadata",
    )
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
    if args.finish_attacks and not (args.first_creature and args.native_metadata):
        parser.error("--finish-attacks requires --first-creature --native-metadata")
    if args.select_attacker and (
        not (args.first_creature and args.native_metadata) or args.finish_attacks
    ):
        parser.error(
            "--select-attacker requires --first-creature --native-metadata and excludes --finish-attacks"
        )
    if args.finish_selected_attack and not args.select_attacker:
        parser.error("--finish-selected-attack requires --select-attacker")
    if args.declared_priority and not args.finish_selected_attack:
        parser.error("--declared-priority requires --finish-selected-attack")
    if args.combat_damage and not args.declared_priority:
        parser.error("--combat-damage requires --declared-priority")
    if args.complete_combat and not args.combat_damage:
        parser.error("--complete-combat requires --combat-damage")
    if args.blocked_combat and (not args.declared_priority or args.combat_damage):
        parser.error(
            "--blocked-combat requires --declared-priority and excludes --combat-damage"
        )
    if args.blocked_damage and not args.blocked_combat:
        parser.error("--blocked-damage requires --blocked-combat")
    if args.loop_turn and not args.complete_combat:
        parser.error("--loop-turn requires --complete-combat")
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
        expected["unity_casting_ability_confirmed"] = False
        expected["unity_followup_priority_submitted"] = False
        expected["unity_battlefield_transition_observed"] = False
        expected["unity_followup_priority_confirmed"] = False
        expected["unity_post_resolution_priority_submitted"] = False
        expected["unity_post_resolution_priority_confirmed"] = False
    evidence = None
    if args.finish_attacks or args.select_attacker:
        expected.update(
            native_attack_source_offered=True,
            native_empty_attack_submitted=not args.select_attacker,
            native_combat_advanced=not args.select_attacker,
            unity_attack_finish_submitted=False,
            unity_attack_finish_confirmed=False,
            unity_combat_priority_submitted=False,
            unity_combat_priority_confirmed=False,
        )
    if args.select_attacker:
        expected.update(
            native_attacker_selected=True,
            native_attack_assignment_observed=True,
            native_attack_selection_open=not args.finish_selected_attack,
        )

    if args.finish_selected_attack:
        expected.update(
            native_selected_attack_finished=True, native_declared_attack_observed=True
        )

    if args.declared_priority:
        expected.update(
            native_declared_priority_submitted=True,
            native_declared_priority_observed=True,
        )

    if args.combat_damage:
        expected.update(
            native_combat_damage_pass_submitted=True,
            native_combat_damage_life_change_observed=True,
        )

    if args.complete_combat:
        expected.update(
            native_postcombat_main_observed=True,
            native_combat_cleared=True,
        )

    if args.blocked_combat:
        expected.update(
            native_blocking_fixture=True,
            native_blocker_projection_validated=True,
            native_blockers_observed=True,
        )

    if args.blocked_damage:
        expected.update(
            native_blocked_damage_pass_submitted=True,
            native_blocker_damage_observed=True,
        )

    if args.loop_turn:
        expected.update(
            native_next_human_turn_observed=True,
            native_own_draw_observed=True,
            native_source_untapped=True,
            native_next_turn_actions_offered=True,
        )

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
                *(["-Dmanaforge.loopTurn=true"] if args.loop_turn else []),
                *(["-Dmanaforge.blockedDamage=true"] if args.blocked_damage else []),
                *(["-Dmanaforge.blockedCombat=true"] if args.blocked_combat else []),
                *(["-Dmanaforge.completeCombat=true"] if args.complete_combat else []),
                *(["-Dmanaforge.combatDamage=true"] if args.combat_damage else []),
                *(
                    ["-Dmanaforge.declaredPriority=true"]
                    if args.declared_priority
                    else []
                ),
                *(
                    ["-Dmanaforge.finishAttacks=true"]
                    if args.finish_attacks or args.select_attacker
                    else []
                ),
                *(
                    ["-Dmanaforge.finishSelectedAttack=true"]
                    if args.finish_selected_attack
                    else []
                ),
                *(["-Dmanaforge.selectAttacker=true"] if args.select_attacker else []),
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
            process.wait(
                timeout=240 if args.finish_attacks or args.select_attacker else 120
            )
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
                    "finish_attacks",
                    "turn_loop",
                }:
                    print("Java live opening failed at stage: " + stage, flush=True)
                if failed.get("code") in {
                    "LIVE_OPENING_UNSUPPORTED_PREGAME",
                    "LIVE_OPENING_TIMEOUT_OR_CANCELLED",
                    "LIVE_OPENING_ENGINE_FAILED",
                    "LIVE_OPENING_QUEUE_LIMIT",
                    "LIVE_OPENING_PIN",
                    "LIVE_TURN_UNSUPPORTED_DECISION",
                    "LIVE_TURN_LOOP_UNPROVEN",
                }:
                    print(failed["code"], flush=True)
                if failed.get("decision_family") in {
                    "GAME_ASK",
                    "GAME_CHOOSE_CHOICE",
                    "GAME_TARGET",
                    "GAME_SELECT",
                }:
                    print("Decision family: " + failed["decision_family"], flush=True)
            if args.loop_turn and process.returncode == 0 and len(raw) <= 4096:
                cleanup_discard = json.loads(raw).get("native_cleanup_discard_observed")
                if type(cleanup_discard) is not bool:
                    raise transport.ProofError("LIVE_TURN_DISCARD_SHAPE")
                expected["native_cleanup_discard_observed"] = cleanup_discard
            if args.declared_priority and process.returncode == 0 and len(raw) <= 4096:
                blockers = json.loads(raw).get("native_blockers_observed")
                if (
                    type(blockers) is not bool
                    or args.blocked_combat
                    and blockers is not True
                ):
                    raise transport.ProofError("LIVE_DECLARED_BLOCKERS_SHAPE")
                expected["native_blockers_observed"] = blockers
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
        "Real XMage completed the opposing turn and returned to the human main phase with native draw, untap and any cleanup discard observed."
        if args.loop_turn
        else "Real XMage marked one damage on the same native Ornithopter blocker in COMBAT_DAMAGE; both life totals unchanged in the public fixture."
        if args.blocked_damage
        else "Real XMage declared visible AI blockers against the selected Memnite; the read-only public assignment validated. No blocked-damage or human blocker-choice proof."
        if args.blocked_combat
        else "Real XMage observed the explicit pass to postcombat main; combat cleared with source incarnation and life totals unchanged."
        if args.complete_combat
        else "Real XMage accepted the explicit damage-window pass; native combat-damage step and one-point defender life decrease observed in the public 1/1 fixture."
        if args.combat_damage
        else "Real XMage accepted one explicit post-declaration priority pass and exposed the next guarded combat state. No damage proof."
        if args.declared_priority
        else "Real XMage accepted explicit selection and Finish attacks; the same attacker remained assigned at guarded native priority. No blocking or damage proof."
        if args.finish_selected_attack
        else "Real XMage accepted an explicit attacker choice and assigned its defender; declaration remains open; duplicate suppression and cleanup passed."
        if args.select_attacker
        else "Real XMage offered the cast source for attacking, accepted explicit Finish attacks with no attackers, and returned to priority; duplicate suppression and cleanup passed. No Unity combat integration."
        if args.finish_attacks
        else "Real XMage creature cast and resolved; stack cleared and 1/1 Memnite observed, duplicate receipts reused; cleanup passed. Unity casting remains pending."
        if args.first_creature
        else "Real XMage opening projected; authenticated boolean submitted once, duplicate receipt reused and engine advancement observed; cleanup passed. Unity integration remains pending."
    )


if __name__ == "__main__":
    main()
