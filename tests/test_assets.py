from __future__ import annotations

from pathlib import Path

import pytest

from ha_streamdeck_gui.assets import (
    AssetsError,
    asset_path,
    list_assets,
    resolve_assets_dir,
    save_asset,
)
from ha_streamdeck_gui.settings import AppSettings


def test_default_assets_dir_next_to_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "streamdeck.yaml"
    settings = AppSettings(streamdeck_yaml_path=str(yaml_path))
    assert resolve_assets_dir(settings) == tmp_path / "assets"


def test_explicit_assets_dir() -> None:
    settings = AppSettings(assets_dir="/opt/streamdeck/icons")
    assert resolve_assets_dir(settings) == Path("/opt/streamdeck/icons")


def test_rejects_missing_dir_config() -> None:
    with pytest.raises(AssetsError):
        resolve_assets_dir(AppSettings())


def test_strips_directory_components(tmp_path: Path) -> None:
    assert asset_path(tmp_path, "../secret.png") == tmp_path.resolve() / "secret.png"
    assert asset_path(tmp_path, "/etc/passwd.png") == tmp_path.resolve() / "passwd.png"


def test_rejects_bad_type(tmp_path: Path) -> None:
    with pytest.raises(AssetsError):
        save_asset(tmp_path, "notes.txt", b"hello")


def test_save_and_list(tmp_path: Path) -> None:
    saved = save_asset(tmp_path, "Kitchen Light.png", b"\x89PNG")
    assert saved["name"] == "Kitchen_Light.png"
    assert Path(saved["path"]).read_bytes() == b"\x89PNG"
    names = [item["name"] for item in list_assets(tmp_path)]
    assert names == ["Kitchen_Light.png"]
