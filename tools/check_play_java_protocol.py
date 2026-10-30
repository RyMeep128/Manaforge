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
    args = parser.parse_args()
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


if __name__ == "__main__":
    main()
