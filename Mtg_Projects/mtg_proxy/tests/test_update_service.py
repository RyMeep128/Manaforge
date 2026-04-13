import pytest

from services import update_service


def release_payload(tag_name="v0.1.1", assets=None, html_url="https://github.test/release"):
    return {
        "tag_name": tag_name,
        "name": tag_name,
        "html_url": html_url,
        "assets": assets
        if assets is not None
        else [
            {
                "name": "PrintProxyPrep-0.1.1-win.zip",
                "browser_download_url": "https://github.test/download.zip",
            }
        ],
    }


def test_is_newer_version_detects_newer_same_and_v_prefix():
    assert update_service.is_newer_version("v0.1.1", "0.1.0") is True
    assert update_service.is_newer_version("0.1.0", "0.1.0") is False
    assert update_service.is_newer_version("0.1", "0.1.0") is False


def test_parse_latest_release_returns_update_with_windows_zip_asset():
    result = update_service.parse_latest_release(release_payload(), "0.1.0")

    assert result.update_available is True
    assert result.current_version == "0.1.0"
    assert result.latest_version == "0.1.1"
    assert result.release_url == "https://github.test/release"
    assert result.asset_name == "PrintProxyPrep-0.1.1-win.zip"
    assert result.asset_url == "https://github.test/download.zip"


def test_parse_latest_release_uses_name_when_tag_is_missing():
    payload = release_payload(tag_name="v0.1.1")
    payload["tag_name"] = ""

    result = update_service.parse_latest_release(payload, "0.1.0")

    assert result.update_available is True
    assert result.latest_version == "0.1.1"


def test_parse_latest_release_same_version_does_not_require_zip_asset():
    result = update_service.parse_latest_release(
        release_payload(tag_name="v0.1.0", assets=[]),
        "0.1.0",
    )

    assert result.update_available is False
    assert result.asset_name is None
    assert result.asset_url is None


def test_parse_latest_release_missing_windows_zip_reports_clean_failure():
    with pytest.raises(update_service.UpdateCheckError, match="Windows release zip"):
        update_service.parse_latest_release(
            release_payload(
                assets=[
                    {
                        "name": "PrintProxyPrep-0.1.1-mac.zip",
                        "browser_download_url": "https://github.test/download.zip",
                    }
                ]
            ),
            "0.1.0",
        )


def test_parse_latest_release_rejects_malformed_release_version():
    with pytest.raises(update_service.UpdateCheckError, match="Invalid version"):
        update_service.parse_latest_release(release_payload(tag_name="banana"), "0.1.0")


def test_check_for_update_uses_supplied_fetcher():
    result = update_service.check_for_update("0.1.0", fetch_json_fn=lambda: release_payload())

    assert result.update_available is True
    assert result.latest_version == "0.1.1"

