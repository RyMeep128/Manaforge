"""Focused Java payment policy checks; optional read-only pinned XMage API inspection.

No engine process is started, no runtime is downloaded or modified, and this is
not real-game payment acceptance. --verify-pinned-api checks binary provenance
before javap inspects any engine class.
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
    parser.add_argument("--javap", type=Path)
    args = parser.parse_args()
    compiler, runtime = shutil.which("javac"), shutil.which("java")
    if not compiler or not runtime:
        parser.error("A JDK with javac and java is required")
    with tempfile.TemporaryDirectory(prefix="manaforge-payment-") as output:
        sources = [PLAY / "java/payment/manaforge/payment/PaymentCoordinator.java",
                   PLAY / "java/payment-test/manaforge/payment/PaymentCoordinatorChecks.java"]
        subprocess.run([compiler, "--release", "8", "-d", output, *map(str, sources)], check=True, timeout=60)
        subprocess.run([runtime, "-cp", output, "manaforge.payment.PaymentCoordinatorChecks"], check=True, timeout=30)
    if not args.verify_pinned_api:
        return
    javap = str(args.javap) if args.javap else shutil.which("javap")
    if not javap:
        parser.error("--verify-pinned-api requires javap on PATH or --javap")
    manifest = json.loads((PLAY / "artifacts.json").read_text())
    engine = PLAY / "mage-full_1.4.62-dev_2026-10-03_20-47"
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
        "mage.player.human.HumanPlayer": ["playMana(mage.abilities.Ability,", "playManaAbilities(java.util.UUID,", "currentlyUnpaidMana"],
        "mage.players.net.UserData": ["setManaPoolAutomatic(boolean)", "setManaPoolAutomaticRestricted(boolean)"],
        "mage.players.PlayerImpl": ["setPayManaMode(boolean)"],
    }
    classpath = os.pathsep.join(str(engine / key) for key in jars)
    for name, signatures in expected.items():
        report = subprocess.run([javap, "-p", "-classpath", classpath, name], capture_output=True, text=True, check=True, timeout=30)
        if not all(signature in report.stdout for signature in signatures):
            raise SystemExit("Pinned payment API signature mismatch: " + name)
    print("Pinned XMage payment APIs: 5 classes verified against artifact hashes; inspection only, no real-game acceptance")


if __name__ == "__main__":
    main()
