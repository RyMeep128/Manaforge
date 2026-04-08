from pathlib import Path

import config
import constants


def test_app_paths_split_install_and_data_dirs():
    assert Path(constants.app_dir).name == "mtg_proxy"
    assert Path(constants.resource_dir) == Path(constants.app_dir)
    assert Path(constants.cwd) == Path(constants.data_dir)
    assert Path(constants.data_dir).name in {"PrintProxyPrep", ".pytest_tmp_data"}


def test_load_config_returns_defaults_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "cwd", str(tmp_path))

    cfg = config.load_config()

    assert cfg.VibranceBump is False
    assert cfg.MaxDPI == 1200
    assert cfg.DefaultPageSize == "Letter"
    assert cfg.EnableUncrop is True
    assert cfg.DisplayColumns == 5
    assert cfg.HighResBackendURL == "https://mpcfill.com/"
    assert cfg.HighResCacheTTLSeconds == 60 * 60
    assert cfg.HighResSearchCacheMemoryMB == 24
    assert cfg.HighResImageCacheMemoryMB == 64
    assert cfg.OnlineMode is True


def test_save_config_and_load_config_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "cwd", str(tmp_path))

    cfg = config.GlobalConfig()
    cfg.VibranceBump = True
    cfg.MaxDPI = 600
    cfg.DefaultPageSize = "A4"
    cfg.EnableUncrop = False
    cfg.DisplayColumns = 7
    cfg.HighResBackendURL = "https://example.com/"
    cfg.HighResCacheTTLSeconds = 30
    cfg.HighResSearchCacheMemoryMB = 8
    cfg.HighResImageCacheMemoryMB = 16
    cfg.OnlineMode = False

    config.save_config(cfg)
    loaded = config.load_config()

    assert (tmp_path / "config.ini").exists()
    assert loaded.VibranceBump is True
    assert loaded.MaxDPI == 600
    assert loaded.DefaultPageSize == "A4"
    assert loaded.EnableUncrop is False
    assert loaded.DisplayColumns == 7
    assert loaded.HighResBackendURL == "https://example.com/"
    assert loaded.HighResCacheTTLSeconds == 30
    assert loaded.HighResSearchCacheMemoryMB == 8
    assert loaded.HighResImageCacheMemoryMB == 16
    assert loaded.OnlineMode is False
