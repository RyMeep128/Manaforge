"""Optional, explicitly compatible XMage releases; never update a running game."""

from __future__ import annotations

import json
from pathlib import Path
import re
import stat
import sys
import uuid
import zipfile

from mtg_core.downloads import (
    atomic_json,
    get_download_manager,
    DownloadCancelled,
    check_space,
)
from mtg_print.update_service import fetch_latest_release_json, _version_parts
from . import runtime_distribution as runtime

REPOSITORY = "https://github.com/RyMeep128/Manaforge/releases/download/"
API = "https://api.github.com/repos/RyMeep128/Manaforge/releases?per_page=100"


def online():
    from mtg_print.config import CFG

    if not CFG.OnlineMode:
        raise ValueError(
            "Offline mode is enabled. Connect before checking XMage updates."
        )


def validate_offer(manifest):
    version = manifest.get("component_version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+-(?:alpha|beta)\.1", version):
        raise ValueError("Invalid XMage component version")
    if not runtime.compatible(manifest):
        raise ValueError("This XMage release requires a different Manaforge version.")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", manifest.get("payload_sha256", ""))
        or not isinstance(manifest.get("size"), int)
        or not 0 < manifest["size"] <= 4 * 1024**3
        or manifest.get("url")
        != REPOSITORY + "xmage-v" + version + "/Manaforge-XMage-Windows.zip"
    ):
        raise ValueError("Invalid XMage release download")
    return manifest


def installed_manifest():
    root = runtime.selected_engine(verify_payload=False)
    return (
        (
            runtime.approved_record(root)
            or runtime.read_manifest(root / "component.json")
        )
        if root
        else None
    )


def check(*, cancel, downloader=None):
    online()
    if sys.platform != "win32":
        raise ValueError("XMage component updates currently support Windows x64 only.")
    downloader = downloader or get_download_manager()
    offers = []
    found = False
    for page in range(1, 11):
        releases = fetch_latest_release_json(API + "&page=" + str(page))
        if not isinstance(releases, list):
            raise ValueError("Invalid XMage releases response")
        for release in releases:
            if cancel.is_set():
                raise DownloadCancelled("XMage check cancelled")
            tag = release.get("tag_name", "")
            if release.get("draft") or not re.fullmatch(
                r"xmage-v\d+\.\d+\.\d+-(?:alpha|beta)\.1", tag
            ):
                continue
            assets = [
                a
                for a in release.get("assets", [])
                if a.get("name") == "xmage-component.json"
            ]
            if len(assets) != 1:
                continue
            found = True
            url = REPOSITORY + tag + "/xmage-component.json"
            if assets[0].get("browser_download_url") != url:
                raise ValueError("Unexpected XMage manifest source")
            path = runtime.component_root() / "downloads" / tag / "component.json"
            downloader.download(url, path, max_bytes=2 * 1024**2, cancel=cancel)
            manifest = runtime.read_manifest(path)
            if not runtime.compatible(manifest):
                continue
            validate_offer(manifest)
            if tag != "xmage-v" + manifest["component_version"]:
                raise ValueError("XMage release tag does not match its manifest")
            offers.append(manifest)
        if len(releases) < 100:
            break
    if not found:
        raise ValueError("No XMage component releases have been published yet.")
    if not offers:
        raise ValueError("No XMage release is approved for this Manaforge version.")
    newest = max(offers, key=lambda m: _version_parts(m["component_version"]))
    installed = installed_manifest()
    if installed and _version_parts(newest["component_version"]) <= _version_parts(
        installed["component_version"]
    ):
        return None
    return newest


def extract(archive, destination, manifest, cancel):
    expected = manifest["files"]
    seen = set()
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        expanded = sum(entry.file_size for entry in members)
        if expanded > 12 * 1024**3 or len(members) > 50000:
            raise ValueError("XMage archive exceeds extraction limits")
        check_space(destination, expanded)
        for entry in members:
            if cancel.is_set():
                raise DownloadCancelled("XMage extraction cancelled; retry the update.")
            name = entry.filename.rstrip("/")
            path = runtime.safe_path(destination, name)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or (entry.external_attr & 0x400):
                raise ValueError("Linked XMage archive entry")
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            if name not in expected or name in seen:
                raise ValueError("Unexpected or duplicated XMage archive file")
            seen.add(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as src, path.open("xb") as dst:
                while chunk := src.read(1024 * 1024):
                    if cancel.is_set():
                        raise DownloadCancelled(
                            "XMage extraction cancelled; retry the update."
                        )
                    dst.write(chunk)
    if seen != set(expected):
        raise ValueError("Incomplete XMage archive")
    runtime.verify(destination, manifest)


def health(root, cancel):
    from .connection_proof import run_proof, DEFAULT_JDK

    result = run_proof(
        Path(root), DEFAULT_JDK, cancel=cancel, payment_context_probe=True
    )
    if not result.get("success"):
        raise ValueError(
            "XMage startup verification failed; the previous engine remains active."
        )


def install(manifest, *, cancel, progress, downloader=None):
    online()
    validate_offer(manifest)
    with runtime.ownership():
        root = runtime.component_root()
        downloader = downloader or get_download_manager()
        archive = root / "downloads" / (manifest["payload_sha256"] + ".zip")
        downloader.download(
            manifest["url"],
            archive,
            sha256=manifest["payload_sha256"],
            size=manifest["size"],
            max_bytes=4 * 1024**3,
            cancel=cancel,
            progress=progress,
        )
        identity = manifest["bundle_id"] + "-" + manifest["payload_sha256"][:12]
        target = root / "installed" / identity
        if not target.exists():
            staging = root / "staging" / uuid.uuid4().hex
            staging.mkdir(parents=True)
            extract(archive, staging, manifest, cancel)
            atomic_json(staging / "component.json", manifest)
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(target)
        runtime.verify(target, manifest)
        atomic_json(root / "approved" / (identity + ".json"), manifest)
        progress(dict(phase="Verifying XMage startup"))
        health(target, cancel)
        if cancel.is_set():
            raise DownloadCancelled("XMage update cancelled before activation.")
        runtime.activate(identity)
        return manifest


def rollback(*, cancel, progress):
    with runtime.ownership():
        state = json.loads(
            (runtime.component_root() / "active.json").read_text(encoding="utf-8")
        )
        previous = state.get("previous")
        if previous is None:
            # No external predecessor: remove the override and use the bundled engine.
            root = runtime.bundled_root() / "xmage"
            runtime.verify_bundled()
            health(root, cancel)
            if cancel.is_set():
                raise DownloadCancelled("XMage rollback cancelled.")
            atomic_json(
                runtime.component_root() / "active.json",
                dict(active=None, previous=state.get("active")),
            )
            return runtime.read_manifest(root / "component.json")
        if not re.fullmatch(r"[0-9a-f-]+", previous):
            raise ValueError("Invalid previous XMage identity")
        root = runtime.component_root() / "installed" / previous
        manifest = runtime.approved_record(root)
        if not manifest:
            raise ValueError(
                "Previous XMage engine is incompatible with this Manaforge version."
            )
        runtime.verify(root, manifest)
        health(root, cancel)
        if cancel.is_set():
            raise DownloadCancelled("XMage rollback cancelled.")
        runtime.activate(previous)
        return manifest
