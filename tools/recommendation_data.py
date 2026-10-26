"""Build, stage and publish recommendation data; tests/validation run in CI."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Mtg_Projects" / "mtg_core"))

from mtg_core.datasets import DatasetInstaller, parse_manifest
from mtg_core.downloads import file_sha256
from mtg_core.paths import core_data_root
from mtg_core.recommendation_distribution import APPROVED_SOURCES, validate_bundle
from mtg_core.recommendation_packaging import build_distribution


REPOSITORY = "RyMeep128/Manaforge"
FEED_TAG = "recommendation-data-latest-alpha.1"


def assets(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    entries = parse_manifest(manifest)
    if not entries:
        raise ValueError("A published manifest must contain actual datasets")
    names = set()
    for entry in entries:
        source = entry.dataset_id.removeprefix("recommendations-")
        name = urllib.parse.urlsplit(entry.url).path.rsplit("/", 1)[-1]
        if (
            source not in APPROVED_SOURCES
            or entry.schema_version != 1
            or entry.format != "zip"
            or entry.category != "recommendations"
            or not re.fullmatch(source + r"-[a-f0-9]{16}\.zip", name)
        ):
            raise ValueError("Unsupported publication asset")
        if name in names:
            raise ValueError("Duplicate publication asset")
        names.add(name)
        path = directory / name
        if path.stat().st_size != entry.size or file_sha256(path) != entry.sha256:
            raise ValueError("Publication asset size/checksum mismatch")
        yield entry, path


def validate_distribution(directory):
    for entry, path in assets(directory):
        with TemporaryDirectory(prefix="verify-") as temporary:
            DatasetInstaller._extract(
                path, Path(temporary), entry.expanded_size, threading.Event(), None
            )
            validate_bundle(
                temporary, entry.dataset_id.removeprefix("recommendations-")
            )
    print("Processed recommendation assets validated.", flush=True)


class GitHub:
    def __init__(self, repository, *, git_credentials=False):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid GitHub repository")
        self.repository = repository
        self.token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self.token and git_credentials:
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
            result = subprocess.run(
                ["git", "credential", "fill"],
                input="protocol=https\nhost=github.com\n\n",
                text=True,
                capture_output=True,
                env=env,
                timeout=15,
            )
            values = dict(
                line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
            )
            self.token = values.get("password")
        if not self.token:
            raise RuntimeError(
                "Set GH_TOKEN or use --git-credentials with existing GitHub credentials"
            )
        self.base = "https://api.github.com/repos/" + repository

    def request(self, path, *, method="GET", data=None, file=None):
        url = path if path.startswith("https://") else self.base + path
        if urllib.parse.urlsplit(url).hostname not in (
            "api.github.com",
            "uploads.github.com",
        ):
            raise ValueError("Unexpected GitHub API host")
        headers = {
            "Authorization": "Bearer " + self.token,
            "User-Agent": "Manaforge data publisher",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if file:
            headers.update(
                {
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(Path(file).stat().st_size),
                }
            )
            with open(file, "rb") as stream:
                request = urllib.request.Request(
                    url, data=stream, headers=headers, method=method
                )
                with urllib.request.urlopen(request, timeout=300) as response:
                    raw = response.read(4 * 1024**2)
        else:
            body = json.dumps(data).encode() if data is not None else None
            if body:
                headers["Content-Type"] = "application/json"
            with urllib.request.urlopen(
                urllib.request.Request(url, data=body, headers=headers, method=method),
                timeout=60,
            ) as response:
                raw = response.read(4 * 1024**2)
        return json.loads(raw) if raw else None

    def release(self, tag):
        # Listing also finds drafts whose tag has not been created yet.
        for page in range(1, 11):
            releases = self.request(f"/releases?per_page=100&page={page}")
            for release in releases:
                if release["tag_name"] == tag:
                    return release
            if len(releases) < 100:
                return None
        raise RuntimeError("Release listing limit reached")

    def upload(self, release, path, *, name=None):
        path = Path(path)
        checksum = file_sha256(path)
        name = name or path.name
        existing = next((a for a in release["assets"] if a["name"] == name), None)
        if existing:
            if (
                existing.get("label") == "sha256:" + checksum
                and existing["size"] == path.stat().st_size
            ):
                return existing
            raise ValueError(
                "An immutable release asset already exists with different content"
            )
        url = (
            release["upload_url"].split("{", 1)[0]
            + "?"
            + urllib.parse.urlencode({"name": name, "label": "sha256:" + checksum})
        )
        return self.request(url, method="POST", file=path)


def stage(github, directory, commit, branch, dispatch):
    document = json.loads(
        (Path(directory) / "manifest.json").read_text(encoding="utf-8")
    )
    version = document["version"]
    if not re.fullmatch(
        r"[0-9][A-Za-z0-9.-]*-(?:alpha|beta)\.1", version
    ) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Use a prerelease dataset version and full committed SHA")
    items = list(assets(directory))
    tag = "recommendations-" + version
    for entry, path in items:
        expected = f"https://github.com/{github.repository}/releases/download/{tag}/{path.name}"
        if entry.url != expected or entry.version != version:
            raise ValueError(
                "Manifest release URLs/version do not match publication target"
            )
    release = github.release(tag)
    if release and (not release["draft"] or release["target_commitish"] != commit):
        raise ValueError(
            "Existing immutable release or target commit mismatch; choose a new dataset version"
        )
    if not release:
        release = github.request(
            "/releases",
            method="POST",
            data=dict(
                tag_name=tag,
                target_commitish=commit,
                name="Recommendation data " + version,
                draft=True,
                prerelease=True,
                body="Processed recommendation datasets. No card database, artwork, raw decks, or collector response caches.",
            ),
        )
    for _, path in items:
        github.upload(release, path)
    github.upload(release, Path(directory) / "manifest.json")
    print("Staged draft: " + release["html_url"], flush=True)
    if dispatch:
        github.request(
            "/actions/workflows/tests.yml/dispatches",
            method="POST",
            data={"ref": branch, "inputs": {"recommendation_release_tag": tag}},
        )
        print(
            "CI requested. Publication waits for tests and generated-asset validation.",
            flush=True,
        )


def promote(github, directory, commit):
    document = json.loads(
        (Path(directory) / "manifest.json").read_text(encoding="utf-8")
    )
    version = document["version"]
    if not re.fullmatch(r"[0-9][A-Za-z0-9.-]*-(?:alpha|beta)\.1", version):
        raise ValueError("A dataset prerelease version is required")
    release = github.release("recommendations-" + version)
    if not release or release["target_commitish"] != commit:
        raise ValueError("Release does not match the CI-tested commit")
    for entry, path in assets(directory):
        if (
            entry.version != version
            or entry.url
            != f"https://github.com/{github.repository}/releases/download/recommendations-{version}/{path.name}"
        ):
            raise ValueError("Manifest release destination mismatch")
    validate_distribution(directory)
    if release["draft"]:
        release = github.request(
            "/releases/" + str(release["id"]),
            method="PATCH",
            data={"draft": False, "prerelease": True, "make_latest": "false"},
        )
    elif not release["prerelease"]:
        raise ValueError("Refusing to repurpose a stable release")
    feed = github.release(FEED_TAG)
    if not feed:
        feed = github.request(
            "/releases",
            method="POST",
            data=dict(
                tag_name=FEED_TAG,
                target_commitish=commit,
                name="Latest compatible recommendation data (alpha)",
                draft=True,
                prerelease=True,
                body="Mutable manifest only. Dataset archives live in immutable versioned prereleases.",
            ),
        )
        github.upload(feed, Path(directory) / "manifest.json")
        github.request(
            "/releases/" + str(feed["id"]),
            method="PATCH",
            data={"draft": False, "prerelease": True, "make_latest": "false"},
        )
    else:
        # Upload first. Preserve the previous manifest for recovery, and restore
        # its name if swapping the feed fails. Never remove versioned archives.
        pending = next(
            (a for a in feed["assets"] if a["name"] == "manifest.next.json"), None
        )
        if pending:
            github.request("/releases/assets/" + str(pending["id"]), method="DELETE")
            feed["assets"].remove(pending)
        new = github.upload(
            feed, Path(directory) / "manifest.json", name="manifest.next.json"
        )
        previous = next(
            (a for a in feed["assets"] if a["name"] == "manifest.previous.json"), None
        )
        if previous:
            github.request("/releases/assets/" + str(previous["id"]), method="DELETE")
        old = next((a for a in feed["assets"] if a["name"] == "manifest.json"), None)
        if old:
            github.request(
                "/releases/assets/" + str(old["id"]),
                method="PATCH",
                data={"name": "manifest.previous.json"},
            )
        try:
            github.request(
                "/releases/assets/" + str(new["id"]),
                method="PATCH",
                data={"name": "manifest.json"},
            )
        except Exception:
            if old:
                github.request(
                    "/releases/assets/" + str(old["id"]),
                    method="PATCH",
                    data={"name": "manifest.json"},
                )
            raise
    print("Published: " + release["html_url"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument(
        "--root", type=Path, default=core_data_root() / "recommendations"
    )
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--repository", default=REPOSITORY)
    build.add_argument(
        "--sources", nargs="+", choices=APPROVED_SOURCES, default=APPROVED_SOURCES
    )
    validate = commands.add_parser("validate")
    validate.add_argument("--directory", type=Path, required=True)
    for name in ("stage", "promote"):
        command = commands.add_parser(name)
        command.add_argument("--directory", type=Path, required=True)
        command.add_argument("--repository", default=REPOSITORY)
        command.add_argument("--commit", required=True)
        command.add_argument("--git-credentials", action="store_true")
        if name == "stage":
            command.add_argument("--branch", default="infrastructure-readiness")
            command.add_argument("--dispatch", action="store_true")
    collect = commands.add_parser("collect")
    collect.add_argument("source", choices=APPROVED_SOURCES)
    collect.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "build":
        build_distribution(
            args.root,
            args.output,
            args.version,
            repository=args.repository,
            sources=args.sources,
        )
    elif args.command == "validate":
        validate_distribution(args.directory)
    elif args.command == "collect":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / f"collect_{args.source}.py"),
                *arguments,
            ],
            check=True,
        )
    else:
        github = GitHub(args.repository, git_credentials=args.git_credentials)
        if args.command == "stage":
            stage(github, args.directory, args.commit, args.branch, args.dispatch)
        else:
            promote(github, args.directory, args.commit)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        sys.exit(
            f"GitHub request failed (HTTP {exc.code}); working data and immutable releases were preserved."
        )
