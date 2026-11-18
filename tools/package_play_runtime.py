"""Build the complete immutable Windows gameplay payload before PyInstaller."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
from mtg_play.runtime_distribution import sha256, verify  # noqa: E402
from mtg_play.engine_fork import read_lock, verify_artifacts  # noqa: E402
from mtg_proxy.constants import APP_VERSION  # noqa: E402


def bridge_sources():
    here = ROOT / "Mtg_Projects/mtg_play"
    sources = list((here / "java").glob("*.java"))
    for directory in ("java/organization", "java/organization-wire", "java/organization-native",
                      "protocol/java/manaforge/protocol", "java/payment-xmage", "java/payment"):
        sources.extend((here / directory).rglob("*.java"))
    return sorted(set(sources))


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Linked runtime payload is not supported")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha256(path)
    return result


def package(engine, unity, jdk, output, component_version, compatible_versions):
    if not re.fullmatch(r"\d+\.\d+\.\d+-(?:alpha|beta)\.1", component_version):
        raise ValueError("Only alpha/beta component versions are supported")
    if compatible_versions != [APP_VERSION]:
        raise ValueError("Only the current tested application version may be advertised")
    lock_path = ROOT / "Mtg_Projects/mtg_play/engine-lock.json"
    lock = read_lock(lock_path)
    if (engine / "manaforge-engine-lock.json").read_bytes() != lock_path.read_bytes():
        raise ValueError("Packaging requires the exact app-owned XMage lock")
    verify_artifacts(engine, lock)
    for jar in (engine / "xmage").rglob("*.jar"):
        if jar.relative_to(engine).as_posix() not in lock["artifacts"]:
            raise ValueError("Unpinned engine JAR: " + str(jar))
    if not (unity / "ManaforgePlay.exe").is_file() or not (unity / "UnityPlayer.dll").is_file():
        raise ValueError("A complete Windows Unity player build is required")
    if output.exists():
        raise ValueError("Use a new output directory; existing payloads are never overwritten")
    distribution = output / "distribution"
    target = distribution / "xmage"
    shutil.copytree(engine, target, ignore=lambda directory, names:
                    {"bridge", "component.json"} if Path(directory) == engine else set())
    shutil.copytree(unity, distribution / "unity")
    sources = bridge_sources()
    fingerprint = hashlib.sha256()
    for source in sources:
        fingerprint.update(source.relative_to(ROOT / "Mtg_Projects/mtg_play").as_posix().encode())
        fingerprint.update(b"\0" + source.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    classes = target / "bridge/classes"
    classes.mkdir(parents=True)
    server = target / "xmage/mage-server"
    classpath = os.pathsep.join((str(server / "lib/*"), str(server / "plugins/mage-player-human-1.4.62.jar")))
    subprocess.run([str(jdk / "bin/javac.exe"), "--release", "8", "-encoding", "UTF-8",
                    "-cp", classpath, "-d", str(classes), *map(str, sources)], check=True)
    files = inventory(target)
    archive = output / "Manaforge-XMage-Windows.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zipped.writestr(info, (target / name).read_bytes())
    manifest = dict(schema=1, platform="windows-x64", bundle_id=lock.get("bundle_id", lock["fork_commit"]),
                    fork_commit=lock["fork_commit"], component_version=component_version,
                    compatible_app_versions=compatible_versions, bridge_fingerprint=fingerprint.hexdigest(),
                    java_identity="jre1.8.0_201-windows-x64", files=files,
                    payload_sha256=sha256(archive), size=archive.stat().st_size,
                    url=f"https://github.com/RyMeep128/Manaforge/releases/download/xmage-v{component_version}/Manaforge-XMage-Windows.zip")
    verify(target, manifest)
    raw = json.dumps(manifest, sort_keys=True, indent=2)
    (target / "component.json").write_text(raw, encoding="utf-8")
    (output / "xmage-component.json").write_text(raw, encoding="utf-8")
    (distribution / "unity.json").write_text(json.dumps(dict(schema=1, app_version=APP_VERSION,
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        files=inventory(distribution / "unity")), sort_keys=True), encoding="utf-8")
    (output / "SHA256SUMS-XMage.txt").write_text(
        f"{sha256(archive)}  {archive.name}\n{sha256(output / 'xmage-component.json')}  xmage-component.json\n",
        encoding="utf-8")
    print(json.dumps(dict(distribution=str(distribution), engine=manifest["bundle_id"], bridge=manifest["bridge_fingerprint"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--unity", type=Path, default=ROOT / "Mtg_Projects/mtg_play_unity/Builds/Windows")
    parser.add_argument("--jdk", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "Mtg_Projects/build/gameplay")
    parser.add_argument("--component-version", default=APP_VERSION)
    parser.add_argument("--compatible-app-version", action="append")
    args = parser.parse_args()
    package(args.engine.resolve(), args.unity.resolve(), args.jdk.resolve(), args.output.resolve(),
            args.component_version, args.compatible_app_version or [APP_VERSION])
