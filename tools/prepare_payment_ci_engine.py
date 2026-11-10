"""Prepare the exact approved delivery engine from its hash-pinned Actions artifact."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
from mtg_play.ci_prepare import prepare  # noqa: E402
from mtg_play.engine_fork import read_lock  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--jdk-path", required=True, type=Path)
    args = parser.parse_args()
    lock = read_lock(ROOT / "Mtg_Projects/mtg_play/engine-lock.json")
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
