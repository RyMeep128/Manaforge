"""Compile fixture DTOs and run shared-corpus checks; never launch XMage."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "Mtg_Projects/mtg_play"
PROTOCOL = PLAY / "protocol"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gson", type=Path)
    parser.add_argument(
        "--download-gson",
        action="store_true",
        help="Explicitly allow the pinned CI dependency download",
    )
    parser.add_argument(
        "--dummy-output",
        type=Path,
        help="Export test-only classes under Unity Artifacts for the CSharp dummy exchange",
    )
    args = parser.parse_args()
    if args.dummy_output:
        allowed = (ROOT / "Mtg_Projects/mtg_play_unity/Artifacts").resolve()
        if (
            not args.dummy_output.resolve().is_relative_to(allowed)
            or args.dummy_output.resolve() == allowed
        ):
            parser.error(
                "Dummy output must be a dedicated directory under Unity Artifacts"
            )
    manifest = json.loads((PLAY / "artifacts.json").read_text())
    artifact = "xmage/mage-server/lib/gson-2.13.2.jar"
    compiler = shutil.which("javac")
    runtime = shutil.which("java")
    if not compiler or not runtime:
        parser.error("A JDK with javac and java on PATH is required")
    with tempfile.TemporaryDirectory(prefix="manaforge-protocol-") as directory:
        workspace = Path(directory)
        jar = args.gson or PLAY / "mage-full_1.4.62-dev_2026-10-03_20-47" / artifact
        if not jar.exists():
            if not args.download_gson:
                parser.error(
                    "Pinned Gson missing; supply --gson or explicitly allow --download-gson"
                )
            jar = workspace / "gson.jar"
            with urllib.request.urlopen(
                "https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.13.2/gson-2.13.2.jar",
                timeout=60,
            ) as response:
                jar.write_bytes(response.read(2 * 1024 * 1024))
        if (
            hashlib.sha256(jar.read_bytes()).hexdigest()
            != manifest["artifacts"][artifact]
        ):
            parser.error("Gson SHA-256 does not match the pinned engine artifact")
        sources = [
            PROTOCOL / "java/manaforge/protocol/PlayContracts.java",
            PROTOCOL / "java/manaforge/protocol/LaunchContracts.java",
            PROTOCOL / "java-test/FixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/TextFrame.java",
            PROTOCOL / "java-test/FrameFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/WireEnvelope.java",
            PROTOCOL / "java-test/EnvelopeFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/WireMessages.java",
            PROTOCOL / "java-test/MessageFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/ViewerAuthentication.java",
            PROTOCOL / "java-test/AuthFixtureConsumer.java",
            PROTOCOL / "java-test/DummyGateway.java",
            PROTOCOL / "java/manaforge/protocol/ReceiveContractSchema.java",
            PROTOCOL / "java/manaforge/protocol/ReceiveMessages.java",
            PROTOCOL / "java-test/ReceiveFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/SubmissionLedger.java",
            PROTOCOL / "java-test/LedgerFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/SessionErrors.java",
            PROTOCOL / "java-test/ErrorFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/ReceiveHistory.java",
            PROTOCOL / "java-test/HistoryFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/LoopbackFrameReader.java",
            PROTOCOL / "java-test/DeadlineFixtureConsumer.java",
            PROTOCOL / "java-test/WriteDeadlineFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/GatewayHandshake.java",
            PROTOCOL / "java-test/HandshakeFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/GatewayCommandGate.java",
            PROTOCOL / "java-test/CommandGateFixtureConsumer.java",
            PROTOCOL / "java/manaforge/protocol/GatewaySessionBoundary.java",
            PROTOCOL / "java-test/SessionBoundaryFixtureConsumer.java",
        ]
        subprocess.run(
            [
                compiler,
                "--release",
                "8",
                "-encoding",
                "UTF-8",
                "-cp",
                str(jar),
                "-d",
                str(workspace),
                *map(str, sources),
            ],
            check=True,
            timeout=120,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.FixtureConsumer",
                str(PROTOCOL),
            ],
            check=True,
            timeout=60,
        )

        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.FrameFixtureConsumer",
                str(PROTOCOL / "fixtures/text-frames-v1.json"),
            ],
            check=True,
            timeout=60,
        )

        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.EnvelopeFixtureConsumer",
                str(PROTOCOL / "fixtures/wire-envelopes-v1.json"),
            ],
            check=True,
            timeout=60,
        )

        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.MessageFixtureConsumer",
                str(PROTOCOL / "fixtures/wire-messages-v1.json"),
            ],
            check=True,
            timeout=60,
        )

        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.AuthFixtureConsumer",
                str(PROTOCOL / "fixtures/viewer-auth-v1.json"),
            ],
            check=True,
            timeout=60,
        )

        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.ReceiveFixtureConsumer",
                str(PROTOCOL / "fixtures/wire-receive-v1.json"),
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.LedgerFixtureConsumer",
                str(PROTOCOL / "fixtures/wire-messages-v1.json"),
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.ErrorFixtureConsumer",
                str(PROTOCOL / "fixtures/wire-errors-v1.json"),
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.HistoryFixtureConsumer",
                str(PROTOCOL / "fixtures/receive-history-v1.json"),
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.DeadlineFixtureConsumer",
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.WriteDeadlineFixtureConsumer",
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                runtime,
                "-cp",
                str(workspace) + os.pathsep + str(jar),
                "manaforge.protocol.HandshakeFixtureConsumer",
                str(PROTOCOL / "fixtures/viewer-auth-v1.json"),
            ],
            check=True,
            timeout=60,
        )
        if args.dummy_output:
            output = args.dummy_output.resolve()
            output.mkdir(parents=True, exist_ok=True)
            if any(
                path.is_symlink()
                or (hasattr(path, "is_junction") and path.is_junction())
                for path in output.rglob("*")
            ):
                parser.error("Dummy output must not contain linked paths")
            shutil.copytree(
                workspace / "manaforge", output / "manaforge", dirs_exist_ok=True
            )
            if jar.resolve() != (output / "gson.jar").resolve():
                shutil.copyfile(jar, output / "gson.jar")
            shutil.copyfile(
                PROTOCOL / "fixtures/dummy-session-v1.json",
                output / "dummy-session-v1.json",
            )
            print(
                "Exported test-only Java dummy classes; no credentials or runtime engine"
            )


if __name__ == "__main__":
    main()
