"""Prepare the pinned engine in a NEW isolated CI directory; never update an installation."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import urllib.request
import uuid
import zipfile
from .connection_proof import HERE, DEFAULT_JDK, ProofError, validate_installation


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(artifact: dict, cache: Path, name: str) -> Path:
    archive = cache / (name + ".zip")
    if not archive.exists():
        temporary = cache / (name + "-" + uuid.uuid4().hex + ".part")
        with (
            urllib.request.urlopen(artifact["url"], timeout=60) as source,
            temporary.open("xb") as target,
        ):
            shutil.copyfileobj(source, target)
        if digest(temporary) != artifact["sha256"]:
            raise ProofError("CI_ARCHIVE_HASH_MISMATCH: " + name)
        temporary.rename(archive)
    if digest(archive) != artifact["sha256"]:
        raise ProofError("CI_ARCHIVE_HASH_MISMATCH: " + name)
    return archive


def extract(archive: Path, artifact: dict, destination: Path):
    root = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if not member.filename.startswith(artifact["prefix"]):
                continue
            parts = PurePosixPath(member.filename).parts
            if (
                ".." in parts
                or "\\" in member.filename
                or any(":" in part for part in parts)
                or PurePosixPath(member.filename).is_absolute()
            ):
                raise ProofError("UNSAFE_CI_ARCHIVE_PATH")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ProofError("UNSUPPORTED_CI_ARCHIVE_LINK")
            path = root / artifact["destination"] / Path(*parts)
            if not path.resolve().is_relative_to(root):
                raise ProofError("UNSAFE_CI_ARCHIVE_PATH")
            if member.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, path.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file)


def prepare(destination: Path, jdk: Path, cache: Path | None = None) -> Path:
    destination = destination.resolve()
    if destination.exists():
        raise ProofError("CI_DESTINATION_ALREADY_EXISTS: use a new isolated directory")
    manifest = json.loads((HERE / "ci-artifacts.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ProofError("UNSUPPORTED_CI_ARCHIVE_MANIFEST")
    cache = (cache or destination.parent / "manaforge-xmage-archives").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / (
        destination.name + "-" + uuid.uuid4().hex + ".tmp"
    )
    temporary.mkdir(parents=True)
    for name in ("engine", "runtime"):
        artifact = manifest[name]
        extract(fetch(artifact, cache, name), artifact, temporary)
    validate_installation(temporary, jdk.resolve())
    # Both resolved endpoints must remain under the explicitly requested parent.
    # No deletion, overwrite, or change to an existing bundle is permitted.
    parent = destination.parent.resolve()
    if (
        temporary.resolve().parent != parent
        or destination.resolve().parent != parent
        or destination.exists()
    ):
        raise ProofError("UNSAFE_CI_DESTINATION")
    temporary.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--jdk-path", type=Path, default=DEFAULT_JDK)
    parser.add_argument("--archive-cache", type=Path)
    args = parser.parse_args()
    print(prepare(args.destination, args.jdk_path, args.archive_cache))


if __name__ == "__main__":
    main()
