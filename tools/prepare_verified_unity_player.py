"""Fetch the exact commit's successful Unity Actions player for Windows packaging."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def prepare(repository, commit, destination):
    if destination.exists():
        raise ValueError("Use a fresh Unity player destination")
    runs = api(f"repos/{repository}/actions/workflows/unity-play.yml/runs?head_sha={commit}&per_page=100")["workflow_runs"]
    selected = None
    for run in runs:
        if run["head_sha"] != commit or run["status"] != "completed" or run["conclusion"] != "success":
            continue
        jobs = api(f"repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
        if not jobs or any(job.get("conclusion") != "success" for job in jobs):
            continue
        artifacts = api(f"repos/{repository}/actions/runs/{run['id']}/artifacts?per_page=100")["artifacts"]
        selected = next((a for a in artifacts if a["name"] == "unity-play-" + commit and not a["expired"]), None)
        if selected:
            break
    if selected is None:
        raise SystemExit("VERIFIED_UNITY_PLAYER_UNAVAILABLE: exact-revision successful Unity checks required")
    digest = selected.get("digest", "")
    if not digest.startswith("sha256:") or selected["size_in_bytes"] > 2 * 1024**3:
        raise ValueError("Unity artifact digest or size is invalid")

    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            redirected = super().redirect_request(req, fp, code, msg, hdrs, newurl)
            if redirected is not None:
                redirected.remove_header("Authorization")
            return redirected

    with tempfile.TemporaryDirectory(prefix="manaforge-verified-unity-") as temporary:
        archive = Path(temporary) / "player.zip"
        request = urllib.request.Request(selected["archive_download_url"], headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json", "User-Agent": "Manaforge-release-build",
        })
        with urllib.request.build_opener(Redirect()).open(request, timeout=120) as source, archive.open("wb") as target:
            shutil.copyfileobj(source, target)
        with archive.open("rb") as source:
            if "sha256:" + hashlib.file_digest(source, "sha256").hexdigest() != digest:
                raise ValueError("Unity artifact checksum mismatch")
        with zipfile.ZipFile(archive) as source:
            if source.read("Artifacts/commit.txt").decode("utf-8-sig").strip() != commit:
                raise ValueError("Unity player source revision mismatch")
            prefix = "Builds/Windows/"
            entries = [entry for entry in source.infolist() if entry.filename.startswith(prefix) and not entry.is_dir()]
            if not entries or sum(entry.file_size for entry in entries) > 4 * 1024**3:
                raise ValueError("Unity player payload is missing or oversized")
            root = destination.resolve()
            for entry in entries:
                target = (destination / entry.filename[len(prefix):]).resolve()
                if not target.is_relative_to(root) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe Unity player artifact path")
            names = {entry.filename for entry in entries}
            if not {prefix + "ManaforgePlay.exe", prefix + "UnityPlayer.dll"}.issubset(names):
                raise ValueError("Unity player artifact is incomplete")
            for entry in entries:
                target = destination / entry.filename[len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as data, target.open("xb") as output:
                    shutil.copyfileobj(data, output)
    print("Verified Unity player from " + run["html_url"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    prepare(args.repository, args.commit, Path(__file__).resolve().parents[1] / "Mtg_Projects/mtg_play_unity/Builds/Windows")
