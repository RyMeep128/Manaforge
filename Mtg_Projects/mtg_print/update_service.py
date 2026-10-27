from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sys
import urllib.error
import urllib.request


LATEST_RELEASE_URL = "https://api.github.com/repos/RyMeep128/Manaforge/releases/latest"
PRERELEASES_URL = "https://api.github.com/repos/RyMeep128/Manaforge/releases?per_page=100"
WINDOWS_ZIP_PATTERN = re.compile(r"^(?:Manaforge-Windows|PrintProxyPrep-.+-win)\.zip$", re.IGNORECASE)


class UpdateCheckError(ValueError):
    pass


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    asset_name: str | None = None
    asset_url: str | None = None


def _normalize_version(version: str | None) -> str:
    if version is not None and not isinstance(version, str):
        raise UpdateCheckError(f"Invalid version: {version!r}")
    normalized = (version or "").strip()
    if normalized.lower().startswith("v"):
        normalized = normalized[1:]
    return normalized


def _version_parts(version: str | None) -> tuple:
    normalized = _normalize_version(version)
    match = re.fullmatch(
        r"(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:\.(0|[1-9]\d*))?"
        r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", normalized)
    if match is None:
        raise UpdateCheckError(f"Invalid version: {version!r}")
    identifiers = (match[4] or '').split('.') if match[4] else []
    if any(part.isdigit() and len(part) > 1 and part.startswith('0') for part in identifiers):
        raise UpdateCheckError(f"Invalid version: {version!r}")
    prerelease = tuple((0, int(part)) if part.isdigit() else (1, part)
                       for part in identifiers)
    return (int(match[1]), int(match[2] or 0), int(match[3] or 0),
            not bool(identifiers), prerelease)


def is_newer_version(latest_version: str | None, current_version: str | None) -> bool:
    latest_parts = _version_parts(latest_version)
    current_parts = _version_parts(current_version)
    return latest_parts > current_parts


def _release_version(release: dict) -> str:
    version = _normalize_version(release.get("tag_name") or release.get("name"))
    _version_parts(version)
    return version


def _find_windows_zip_asset(release: dict) -> tuple[str, str] | None:
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not WINDOWS_ZIP_PATTERN.match(name):
            continue
        if name.lower().startswith('printproxyprep-'):
            embedded = name[len('PrintProxyPrep-'):-len('-win.zip')]
            if _normalize_version(embedded) != _release_version(release):
                continue
        if asset.get('size') == 0:
            continue
        url = str(asset.get("browser_download_url") or "")
        if not url.startswith("https://") or asset.get("state", "uploaded") != "uploaded":
            continue
        return name, url
    return None


def parse_latest_release(release: dict, current_version: str) -> UpdateCheckResult:
    if not isinstance(release, dict):
        raise UpdateCheckError("GitHub release response was not a JSON object.")

    if release.get("draft"):
        raise UpdateCheckError("Release is still a draft.")
    latest_version = _release_version(release)
    release_url = str(release.get("html_url") or "")
    update_available = is_newer_version(latest_version, current_version)
    asset = _find_windows_zip_asset(release) if update_available else None
    if update_available and asset is None:
        raise UpdateCheckError("A newer release exists, but it does not include a Windows release zip.")

    asset_name, asset_url = asset if asset is not None else (None, None)
    return UpdateCheckResult(
        current_version=_normalize_version(current_version),
        latest_version=latest_version,
        update_available=update_available,
        release_url=release_url,
        asset_name=asset_name,
        asset_url=asset_url,
    )


def fetch_latest_release_json(url: str = LATEST_RELEASE_URL) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PrintProxyPrep-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise UpdateCheckError(f"Could not reach GitHub Releases: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateCheckError("GitHub Releases returned invalid JSON.") from exc


def _channel(version: str) -> str:
    return _normalize_version(version).split('+')[0].partition('-')[2].split('.')[0]


def check_for_update(current_version: str, fetch_json_fn=None, cancelled_fn=None) -> UpdateCheckResult:
    _version_parts(current_version)
    # Only Windows bundles are published. Never offer them on another OS.
    if sys.platform != 'win32' and fetch_json_fn is None:
        raise UpdateCheckError('Application update packages are currently available for Windows only.')
    if fetch_json_fn is not None:
        releases = fetch_json_fn()
        if isinstance(releases, dict):
            releases = [releases]
    else:
        releases = []
        page = 1
        while True:
            if cancelled_fn is not None and cancelled_fn():
                raise UpdateCheckError('Update check cancelled.')
            batch = fetch_latest_release_json(PRERELEASES_URL + f'&page={page}')
            if not isinstance(batch, list):
                raise UpdateCheckError('GitHub releases response was not a list.')
            releases.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    if not isinstance(releases, list):
        raise UpdateCheckError('GitHub releases response was not a list.')
    channel = _channel(current_version)
    allowed = {'alpha': {'alpha', 'beta', 'rc', ''},
               'beta': {'beta', 'rc', ''}, 'rc': {'rc', ''}}.get(channel, {''})
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft'):
            continue
        try:
            version = _release_version(release)
        except UpdateCheckError:
            continue
        if _channel(version) not in allowed or (not channel and release.get('prerelease')):
            continue
        if _find_windows_zip_asset(release) is not None:
            candidates.append(release)
    if not candidates:
        raise UpdateCheckError('No downloadable Windows application release was found for this channel.')
    newest = max(candidates, key=lambda release: _version_parts(_release_version(release)))
    return parse_latest_release(newest, current_version)
