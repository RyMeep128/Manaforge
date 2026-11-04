"""Focused Java payment policy checks; optional read-only pinned XMage API inspection.

No runtime is downloaded or modified. --verify-pinned-api checks binary provenance
before javap inspects any engine class. --real-game-payment additionally runs
focused native casting/payment acceptance in real game objects, without Unity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "Mtg_Projects/mtg_play"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-pinned-api", action="store_true")
    parser.add_argument("--probe-pinned-helpers", action="store_true",
                        help="Also execute focused native utility-object checks after verifying every runtime JAR")
    parser.add_argument("--real-game-payment", action="store_true",
                        help="Also cast real red creatures against the screenshot board; requires --probe-pinned-helpers")
    parser.add_argument("--javap", type=Path)
    parser.add_argument("--xmage-root", type=Path, default=PLAY / "mage-full_1.4.62-dev_2026-10-03_20-47")
    args = parser.parse_args()
    if args.real_game_payment and not args.probe_pinned_helpers:
        parser.error("--real-game-payment requires --probe-pinned-helpers")
    compiler, runtime = shutil.which("javac"), shutil.which("java")
    if not compiler or not runtime:
        parser.error("A JDK with javac and java is required")
    with tempfile.TemporaryDirectory(prefix="manaforge-payment-") as output:
        sources = [PLAY / "java/payment/manaforge/payment/PaymentCoordinator.java",
                   PLAY / "java/payment-test/manaforge/payment/PaymentCoordinatorChecks.java",
                   PLAY / "java/payment-xmage/manaforge/payment/xmage/ManaResponseExecutor.java",
                   PLAY / "java/payment-native-test/manaforge/payment/NativeManaResponseChecks.java"]
        subprocess.run([compiler, "--release", "8", "-d", output, *map(str, sources)], check=True, timeout=60)
        subprocess.run([runtime, "-cp", output, "manaforge.payment.PaymentCoordinatorChecks"], check=True, timeout=30)
        subprocess.run([runtime, "-cp", output, "manaforge.payment.NativeManaResponseChecks"], check=True, timeout=30)
    if not (args.verify_pinned_api or args.probe_pinned_helpers):
        return
    javap = str(args.javap) if args.javap else shutil.which("javap")
    if not javap:
        parser.error("--verify-pinned-api requires javap on PATH or --javap")
    manifest = json.loads((PLAY / "artifacts.json").read_text())
    engine = args.xmage_root.resolve()
    jars = ["xmage/mage-server/lib/mage-1.4.62.jar",
            "xmage/mage-server/plugins/players/mage-player-human-1.4.62.jar"]
    # Resolve the human plugin by the existing manifest rather than assuming its directory.
    jars[1] = next(key for key in manifest["artifacts"] if key.startswith("xmage/mage-server/") and key.endswith("/mage-player-human-1.4.62.jar"))
    for key in jars:
        if hashlib.sha256((engine / key).read_bytes()).hexdigest() != manifest["artifacts"][key]:
            raise SystemExit("Pinned payment API artifact mismatch")
    expected = {
        "mage.players.ManaPool": ["setAutoPayment(boolean)", "setAutoPaymentRestricted(boolean)"],
        "mage.util.ManaUtil": ["tryToAutoPay(mage.abilities.costs.mana.ManaCost,", "tryToAutoSelectAManaColor(mage.choices.Choice,"],
        "mage.player.human.HumanPlayer": ["playMana(mage.abilities.Ability,", "playManaHandling(mage.abilities.Ability,", "playManaAbilities(java.util.UUID,", "currentlyUnpaidMana", "responseOpenedForAnswer"],
        "mage.players.net.UserData": ["setManaPoolAutomatic(boolean)", "setManaPoolAutomaticRestricted(boolean)"],
        "mage.players.PlayerImpl": ["setPayManaMode(boolean)"],
        "mage.Mana": ["boolean enough(mage.Mana)", "mage.Mana copy()"],
        "mage.abilities.mana.ManaOptions": ["boolean enough(mage.Mana)"],
        "mage.abilities.effects.ContinuousEffects": ["int getTotalEffectsCount()"],
        "mage.game.GameState": ["getTriggers()", "getDelayed()", "getTriggered(java.util.UUID)", "isManaBurn()", "getZoneChangeCounter(java.util.UUID)"],
        "mage.cards.CardImpl": ["boolean caresAboutManaColor(mage.game.Game)"],
        "mage.game.permanent.Permanent": ["getTransformCount()", "isTapped()", "isPhasedIn()", "isFlipped()"],
    }
    classpath = os.pathsep.join(str(engine / key) for key in jars)
    for name, signatures in expected.items():
        report = subprocess.run([javap, "-p", "-classpath", classpath, name], capture_output=True, text=True, check=True, timeout=30)
        if not all(signature in report.stdout for signature in signatures):
            raise SystemExit("Pinned payment API signature mismatch: " + name)
    print("Pinned XMage payment APIs: 11 classes verified against artifact hashes; inspection only, no real-game acceptance")
    if args.probe_pinned_helpers:
        # Do not execute a classpath wildcard or an unverified local dependency.
        dependencies = sorted(key for key in manifest["artifacts"]
                              if key.startswith("xmage/mage-server/lib/") and key.endswith(".jar"))
        dependencies.append(jars[1])
        if args.real_game_payment:
            dependencies.append(next(key for key in manifest["artifacts"] if key.endswith("/mage-game-twoplayerduel-1.4.62.jar")))
        for key in dependencies:
            if hashlib.sha256((engine / key).read_bytes()).hexdigest() != manifest["artifacts"][key]:
                raise SystemExit("Pinned payment helper dependency mismatch")
        native_classpath = os.pathsep.join(str((engine / key).resolve()) for key in dependencies)
        with tempfile.TemporaryDirectory(prefix="manaforge-native-payment-") as output:
            source = PLAY / "java/payment-native-test/manaforge/payment/PinnedPaymentChecks.java"
            adapter = PLAY / "java/payment-xmage/manaforge/payment/xmage/SelectedSourceMana.java"
            response = PLAY / "java/payment-xmage/manaforge/payment/xmage/ManaResponseExecutor.java"
            context_source = PLAY / "java/payment-xmage/manaforge/payment/xmage/ContextHumanPlayer.java"
            bridge_sources = [PLAY / "java" / name for name in ("ManaforgeBridge.java", "ManaforgeServerHost.java", "ManaforgeGameMetadata.java")]
            bridge_sources += [PLAY / "java/ManaforgeMetadataChannel.java", *sorted((PLAY / "protocol/java/manaforge/protocol").glob("*.java"))]
            if args.real_game_payment:
                bridge_sources.append(PLAY / "java/payment-native-test/manaforge/payment/RealPaymentGameChecks.java")
            subprocess.run([compiler, "--release", "8", "-encoding", "UTF-8", "-cp", native_classpath, "-d", output,
                            str(source), str(adapter), str(response), str(context_source),
                            str(PLAY / "java/payment-xmage/manaforge/payment/xmage/OrdinaryManaShape.java"),
                            str(PLAY / "java/payment-xmage/manaforge/payment/xmage/OrdinaryCostCoverage.java"),
                            str(PLAY / "java/payment-xmage/manaforge/payment/xmage/NativePaymentHazards.java"),
                            str(PLAY / "java/payment-xmage/manaforge/payment/xmage/NativePaymentPlan.java"), *map(str, bridge_sources)],
                           check=True, timeout=60)
            subprocess.run([runtime, "-cp", output + os.pathsep + native_classpath,
                            "manaforge.payment.PinnedPaymentChecks"], cwd=output, check=True, timeout=30)
            print("Owned Java bridge compiled against unchanged pinned SDK; no server/game started by this probe")
            if args.real_game_payment:
                subprocess.run([runtime, "-Djava.awt.headless=true", "-cp", output + os.pathsep + native_classpath,
                                "manaforge.payment.RealPaymentGameChecks"], cwd=output, check=True, timeout=60)


if __name__ == "__main__":
    main()
