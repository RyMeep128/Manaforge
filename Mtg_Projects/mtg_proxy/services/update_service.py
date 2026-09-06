from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.request


LATEST_RELEASE_URL = "https://api.github.com/repos/RyMeep128/Manaforge/releases/latest"
PRERELEASES_URL = "https://api.github.com/repos/RyMeep128/Manaforge/releases?per_page=100"
WINDOWS_ZIP_PATTERN = re.compile(r"^PrintProxyPrep-.+-win\.zip$", re.IGNORECASE)


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
    normalized = (version or "").strip()
    if normalized.lower().startswith("v"):
        normalized = normalized[1:]
    return normalized


def _version_parts(version: str | None) -> tuple[int, ...]:
    normalized = _normalize_version(version)
    match = re.fullmatch(r"(\d+(?:\.\d+){0,2})(?:-(alpha|beta|rc)\.(\d+))?", normalized)
    if match is None:
        raise UpdateCheckError(f"Invalid version: {version!r}")
    parts = tuple(int(part) for part in match[1].split('.'))
    return parts + (0,) * (3 - len(parts)) + (
        {None: 3, 'alpha': 0, 'beta': 1, 'rc': 2}[match[2]], int(match[3] or 0))


def is_newer_version(latest_version: str | None, current_version: str | None) -> bool:
    latest_parts = _version_parts(latest_version)
    current_parts = _version_parts(current_version)
    length = max(len(latest_parts), len(current_parts))
    latest_parts = latest_parts + (0,) * (length - len(latest_parts))
    current_parts = current_parts + (0,) * (length - len(current_parts))
    return latest_parts > current_parts


def _release_version(release: dict) -> str:
    version = _normalize_version(release.get("tag_name") or release.get("name"))
    _version_parts(version)
    return version


def _find_windows_zip_asset(release: dict) -> tuple[str, str] | None:
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not WINDOWS_ZIP_PATTERN.match(name):
            continue
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        return name, url
    return None


def parse_latest_release(release: dict, current_version: str) -> UpdateCheckResult:
    if not isinstance(release, dict):
        raise UpdateCheckError("GitHub release response was not a JSON object.")

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


def fetch_latest_release_json(url: str = LATEST_RELEASE_URL) -> dict:
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
    except json.JSONDecodeError as exc:
        raise UpdateCheckError("GitHub Releases returned invalid JSON.") from exc


def check_for_update(current_version: str, fetch_json_fn=None) -> UpdateCheckResult:
    default_fetcher = fetch_json_fn is None
    fetch_json_fn = fetch_json_fn or fetch_latest_release_json
    if '-' not in _normalize_version(current_version):
        return parse_latest_release(fetch_json_fn(), current_version)
    releases = (fetch_json_fn(PRERELEASES_URL) if default_fetcher
                else fetch_json_fn())
    if not isinstance(releases, list):
        raise UpdateCheckError('GitHub prerelease response was not a list.')
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft'):
            continue
        try:
            version = _release_version(release)
        except UpdateCheckError:
            continue
        # Beta users receive beta/RC/stable builds, not experimental alpha builds.
        if '-beta.' in current_version and '-alpha.' in version:
            continue
        candidates.append(release)
    if not candidates:
        return UpdateCheckResult(_normalize_version(current_version),
                                 _normalize_version(current_version), False, '')
    newest = max(candidates, key=lambda release: _version_parts(_release_version(release)))
    return parse_latest_release(newest, current_version)

