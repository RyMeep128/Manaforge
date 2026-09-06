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


@pytest.mark.parametrize('newer,older', [
    ('0.2.0-alpha.2', '0.2.0-alpha.1'),
    ('0.2.0-beta.1', '0.2.0-alpha.9'),
    ('0.2.0', '0.2.0-beta.9'),
    ('0.3.0-alpha.1', '0.2.9-beta.1'),
])
def test_prerelease_version_order(newer, older):
    assert update_service.is_newer_version(newer, older)
    assert not update_service.is_newer_version(older, newer)
    assert not update_service.is_newer_version(newer, newer)


def test_alpha_update_fetches_release_list_and_skips_drafts(monkeypatch):
    urls = []
    def fetch(url):
        urls.append(url)
        return [release_payload('v0.2.0-alpha.1'),
                dict(release_payload('v0.9.0'), draft=True),
                release_payload('not-a-version'), release_payload('v0.1.2-alpha.1')]
    monkeypatch.setattr(update_service, 'fetch_latest_release_json', fetch)
    result = update_service.check_for_update('0.1.2-alpha.1')
    assert result.latest_version == '0.2.0-alpha.1'
    assert result.update_available
    assert urls == [update_service.PRERELEASES_URL]


def test_beta_channel_does_not_offer_alpha():
    result = update_service.check_for_update('0.2.0-beta.1', lambda: [
        release_payload('v0.3.0-alpha.1'), release_payload('v0.2.0-beta.2')])
    assert result.latest_version == '0.2.0-beta.2'


def test_empty_prerelease_channel_reports_no_update():
    assert not update_service.check_for_update('0.1.2-alpha.1', lambda: []).update_available

