"""Server-side settings. The Home Assistant token never leaves this process."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from ha_streamdeck_gui.decks import DeckModelId


def default_config_dir() -> Path:
    override = os.environ.get("HA_STREAMDECK_GUI_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "ha-streamdeck-gui"
    return Path.home() / ".config" / "ha-streamdeck-gui"


def settings_path() -> Path:
    return default_config_dir() / "settings.yaml"


class AppSettings(BaseModel):
    streamdeck_yaml_path: str = ""
    ha_url: str = ""
    ha_token: str = ""
    deck_model: DeckModelId | str = "plus"
    backup_count: int = Field(default=10, ge=1, le=100)
    systemd_service_name: str = ""
    assets_dir: str = ""
    host: str = "0.0.0.0"
    port: int = 8080


class PublicSettings(BaseModel):
    streamdeck_yaml_path: str = ""
    ha_url: str = ""
    ha_token_set: bool = False
    deck_model: str = "plus"
    backup_count: int = 10
    systemd_service_name: str = ""
    assets_dir: str = ""
    resolved_assets_dir: str = ""
    host: str = "0.0.0.0"
    port: int = 8080


def _yaml() -> YAML:
    yaml = YAML()
    yaml.default_flow_style = False
    return yaml


def load_settings() -> AppSettings:
    data: dict[str, Any] = {}
    path = settings_path()
    if path.is_file():
        loaded = _yaml().load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data.update(loaded)
    env_map = {
        "streamdeck_yaml_path": "STREAMDECK_YAML_PATH",
        "ha_url": "HA_URL",
        "ha_token": "HA_TOKEN",
        "deck_model": "DECK_MODEL",
        "backup_count": "BACKUP_COUNT",
        "systemd_service_name": "SYSTEMD_SERVICE_NAME",
        "assets_dir": "ASSETS_DIR",
        "host": "HOST",
        "port": "PORT",
    }
    for field_name, env_name in env_map.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        if field_name in {"backup_count", "port"}:
            data[field_name] = int(raw)
        else:
            data[field_name] = raw
    return AppSettings.model_validate(data)


def save_settings(settings: AppSettings) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump()
    stream = path.open("w", encoding="utf-8")
    try:
        _yaml().dump(payload, stream)
    finally:
        stream.close()
    path.chmod(0o600)
    return path


def public_settings(settings: AppSettings) -> PublicSettings:
    resolved = ""
    if settings.assets_dir:
        resolved = str(Path(settings.assets_dir).expanduser())
    elif settings.streamdeck_yaml_path:
        resolved = str(Path(settings.streamdeck_yaml_path).expanduser().parent / "assets")
    return PublicSettings(
        streamdeck_yaml_path=settings.streamdeck_yaml_path,
        ha_url=settings.ha_url,
        ha_token_set=bool(settings.ha_token),
        deck_model=str(settings.deck_model or "plus"),
        backup_count=settings.backup_count,
        systemd_service_name=settings.systemd_service_name,
        assets_dir=settings.assets_dir,
        resolved_assets_dir=resolved,
        host=settings.host,
        port=settings.port,
    )


def merge_settings(current: AppSettings, updates: dict[str, Any]) -> AppSettings:
    payload = current.model_dump()
    for key, value in updates.items():
        if key == "ha_token":
            if value is None or value == "":
                continue
            payload["ha_token"] = value
            continue
        if key in payload:
            payload[key] = value
    return AppSettings.model_validate(payload)
