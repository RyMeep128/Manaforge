"""Prepare the exact approved delivery engine from its hash-pinned Actions artifact."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
sys.path.insert(0, str(ROOT / "Mtg_Projects/mtg_core"))
from mtg_play.ci_prepare import prepare  # noqa: E402
from mtg_play.engine_fork import read_lock  # noqa: E402


def released_bundle(destination, lock):
    """Durable public release assets remain usable after Actions artifacts expire."""
    from mtg_core.downloads import get_download_manager
    from mtg_play.component_updates import extract, REPOSITORY
    from mtg_play.runtime_distribution import read_manifest, verify
    import uuid
    manager = get_download_manager()
    cache = destination.parent / "released-engine-cache"
    for page in range(1, 11):
        request = urllib.request.Request(
            "https://api.github.com/repos/RyMeep128/Manaforge/releases?per_page=100&page=" + str(page),
            headers={"User-Agent": "Manaforge-release-build"})
        with urllib.request.urlopen(request, timeout=60) as response:
            releases = json.load(response)
        for release in releases:
            tag = release.get("tag_name", "")
            import re
            if release.get("draft") or not re.fullmatch(r"xmage-v\d+\.\d+\.\d+-(alpha|beta)\.1", tag):
                continue
            metadata = cache / tag / "component.json"
            manager.download(REPOSITORY + tag + "/xmage-component.json", metadata, max_bytes=2 * 1024**2)
            manifest = read_manifest(metadata)
            if manifest["bundle_id"] != lock.get("bundle_id", lock["fork_commit"]):
                continue
            url = REPOSITORY + tag + "/Manaforge-XMage-Windows.zip"
            archive = cache / (manifest["payload_sha256"] + ".zip")
            manager.download(url, archive, sha256=manifest["payload_sha256"], size=manifest["size"], max_bytes=4 * 1024**3)
            temporary = destination.parent / ("released-engine-" + uuid.uuid4().hex)
            temporary.mkdir()
            extract(archive, temporary, manifest, threading.Event())
            if (temporary / "manaforge-engine-lock.json").read_bytes() != (ROOT / "Mtg_Projects/mtg_play/engine-lock.json").read_bytes():
                raise ValueError("Released engine does not match the app-owned lock")
            verify(temporary, manifest)
            temporary.rename(destination)
            return True
        if len(releases) < 100:
            break
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--jdk-path", required=True, type=Path)
    args = parser.parse_args()
    lock = read_lock(ROOT / "Mtg_Projects/mtg_play/engine-lock.json")
    if args.destination.exists():
        raise SystemExit("Use a new engine destination")
    if released_bundle(args.destination, lock):
        print("Prepared exact pinned engine from a durable public prerelease")
        return
    expected = lock["ci_artifact_sha256"]
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Manaforge-payment-CI",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    base = "https://api.github.com/repos/RyMeep128/Manaforge-XMage/actions/artifacts"
    artifact = None
    for page in range(1, 11):
        request = urllib.request.Request(
            base + "?per_page=100&page=" + str(page), headers=headers
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            batch = json.load(response)["artifacts"]
        artifact = next(
            (
                item
                for item in batch
                if not item["expired"]
                and item["workflow_run"]["head_sha"] == lock["fork_commit"]
                and item.get("digest") == "sha256:" + expected
            ),
            None,
        )
        if artifact or not batch:
            break
    if artifact is None:
        raise SystemExit(
            "DELIVERY_ENGINE_ARTIFACT_UNAVAILABLE: exact pinned archive required; no stock fallback"
        )
    archive = args.destination.parent / (
        "payment-engine-" + str(artifact["id"]) + ".zip"
    )
    if not archive.exists():
        # GitHub's signed storage redirect must not receive the repository token.
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                result = super().redirect_request(req, fp, code, msg, hdrs, newurl)
                if result is not None:
                    result.remove_header("Authorization")
                return result

        request = urllib.request.Request(
            artifact["archive_download_url"], headers=headers
        )
        with (
            urllib.request.build_opener(Redirect()).open(
                request, timeout=60
            ) as response,
            archive.open("xb") as target,
        ):
            import shutil

            shutil.copyfileobj(response, target)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit("DELIVERY_ENGINE_ARCHIVE_HASH_MISMATCH")
    assemblies = args.destination.parent / ("payment-assemblies-" + str(artifact["id"]))
    assemblies.mkdir(exist_ok=True)
    found = {}
    with zipfile.ZipFile(archive) as source:
        for name in ("mage-server", "mage-client"):
            matches = [
                entry
                for entry in source.namelist()
                if Path(entry).name == name + ".zip"
            ]
            if len(matches) != 1:
                raise SystemExit("DELIVERY_ENGINE_ASSEMBLY_AMBIGUOUS")
            target = assemblies / (name + ".zip")
            raw = source.read(matches[0])
            if hashlib.sha256(raw).hexdigest() != lock["assemblies"][name]:
                raise SystemExit("DELIVERY_ENGINE_ASSEMBLY_HASH_MISMATCH")
            target.write_bytes(raw)
            found[name] = target
    prepare(
        args.destination,
        args.jdk_path,
        fork_server=found["mage-server"],
        fork_client=found["mage-client"],
    )
    print(
        json.dumps(
            {
                "engine_source_sha": lock["fork_commit"],
                "bundle_id": lock["bundle_id"],
                "archive_sha256": expected,
                "artifact_id": artifact["id"],
            }
        )
    )


if __name__ == "__main__":
    main()
