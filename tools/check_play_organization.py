"""Compile and check the pure organization reducer without engine or Unity SDKs."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "Mtg_Projects/mtg_play/java"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jdk-path", type=Path)
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    jdk = args.jdk_path or os.environ.get("JAVA_HOME")
    suffix = ".exe" if os.name == "nt" else ""
    javac = (
        str(Path(jdk) / "bin" / ("javac" + suffix)) if jdk else shutil.which("javac")
    )
    java = str(Path(jdk) / "bin" / ("java" + suffix)) if jdk else shutil.which("java")
    if not javac or not java:
        parser.error("A JDK is required")
    sources = sorted((PLAY / "organization").rglob("*.java")) + sorted(
        (PLAY / "organization-test").rglob("*.java")
    )
    with tempfile.TemporaryDirectory(prefix="manaforge-organization-") as output:
        subprocess.run(
            [
                javac,
                "--release",
                "8",
                "-encoding",
                "UTF-8",
                "-classpath",
                output,
                "-d",
                output,
                *map(str, sources),
            ],
            check=True,
            timeout=60,
        )
        if not args.compile_only:
            subprocess.run(
                [java, "-cp", output, "manaforge.organization.OrganizationChecks"],
                check=True,
                timeout=60,
            )
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    print(
        f"Organization {'compile-only' if args.compile_only else 'checks'} passed: {sha}"
    )


if __name__ == "__main__":
    main()
