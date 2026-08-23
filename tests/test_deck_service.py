from __future__ import annotations

from pathlib import Path

import pytest

from ha_streamdeck_gui.deck_service import (
    DeckServiceError,
    reject_unknown_entities,
    require_render_libraries,
    write_deck_env,
    write_user_unit,
)
from ha_streamdeck_gui.ha import Entity, EntityCache, hass_streamdeck_endpoint
from ha_streamdeck_gui.settings import AppSettings

PLACEHOLDER_HA = "http://192.0.2.10:8123"


def test_http_url_puts_port_on_host() -> None:
    host, protocol = hass_streamdeck_endpoint("http://192.0.2.10:8123")
    assert host == "192.0.2.10:8123"
    assert protocol == "ws"


def test_http_url_defaults_to_8123() -> None:
    host, protocol = hass_streamdeck_endpoint("http://192.0.2.10")
    assert host == "192.0.2.10:8123"
    assert protocol == "ws"


def test_https_keeps_host_when_no_port() -> None:
    host, protocol = hass_streamdeck_endpoint("https://example.ui.nabu.casa")
    assert host == "example.ui.nabu.casa"
    assert protocol == "wss"


def test_write_deck_env_uses_gui_token(tmp_path: Path) -> None:
    yaml_path = tmp_path / "streamdeck.yaml"
    yaml_path.write_text("pages:\n  - name: Home\n    buttons: []\n", encoding="utf-8")
    settings = AppSettings(
        streamdeck_yaml_path=str(yaml_path),
        ha_url=PLACEHOLDER_HA,
        ha_token="test-token-value",
    )
    env_path = write_deck_env(settings)
    text = env_path.read_text(encoding="utf-8")
    assert "HASS_HOST=192.0.2.10:8123" in text
    assert "HASS_TOKEN=test-token-value" in text
    assert f"STREAMDECK_CONFIG={yaml_path.resolve()}" in text
    assert "WEBSOCKET_PROTOCOL=ws" in text
    assert env_path.stat().st_mode & 0o777 == 0o600


def test_require_render_libraries_explains_apt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ha_streamdeck_gui.deck_service.cairo_library_found", lambda: False)
    with pytest.raises(DeckServiceError, match="libcairo2"):
        require_render_libraries()


def test_user_unit_start_limits_are_in_unit_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_path = tmp_path / "streamdeck.yaml"
    yaml_path.write_text("pages:\n  - name: Home\n    buttons: []\n", encoding="utf-8")
    unit = tmp_path / "home-assistant-streamdeck-yaml.service"
    monkeypatch.setattr("ha_streamdeck_gui.deck_service.user_unit_path", lambda: unit)
    write_user_unit(AppSettings(streamdeck_yaml_path=str(yaml_path)))
    text = unit.read_text(encoding="utf-8")
    unit_section, service_section = text.split("[Service]", 1)
    assert "StartLimitBurst=3" in unit_section
    assert "StartLimitIntervalSec=60" in unit_section
    assert "StartLimitBurst" not in service_section
    assert "StartLimitIntervalSec" not in service_section


def test_reject_unknown_entities_blocks_sample_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_path = tmp_path / "streamdeck.yaml"
    yaml_path.write_text(
        "pages:\n  - name: Home\n    buttons:\n      - entity_id: light.kitchen\n",
        encoding="utf-8",
    )
    cache = EntityCache(
        entities=[
            Entity(
                entity_id="light.known_test",
                friendly_name="Sink",
                domain="light",
                state="off",
                attributes={},
            )
        ]
    )
    monkeypatch.setattr("ha_streamdeck_gui.deck_service.refresh_cache", lambda url, token: cache)
    settings = AppSettings(
        streamdeck_yaml_path=str(yaml_path),
        ha_url=PLACEHOLDER_HA,
        ha_token="test-token-value",
    )
    with pytest.raises(DeckServiceError, match="light.kitchen"):
        reject_unknown_entities(settings)


def test_reject_unknown_entities_fails_closed_on_empty_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_path = tmp_path / "streamdeck.yaml"
    yaml_path.write_text("pages:\n  - name: Home\n    buttons: []\n", encoding="utf-8")
    monkeypatch.setattr(
        "ha_streamdeck_gui.deck_service.refresh_cache",
        lambda url, token: EntityCache(),
    )
    settings = AppSettings(
        streamdeck_yaml_path=str(yaml_path),
        ha_url=PLACEHOLDER_HA,
        ha_token="test-token-value",
    )
    with pytest.raises(DeckServiceError, match="no entities"):
        reject_unknown_entities(settings)


def test_reject_unknown_entities_wraps_bad_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_path = tmp_path / "streamdeck.yaml"
    yaml_path.write_text("pages: []\n", encoding="utf-8")
    cache = EntityCache(
        entities=[
            Entity(
                entity_id="light.known_test",
                friendly_name="Test",
                domain="light",
                state="off",
            )
        ]
    )
    monkeypatch.setattr("ha_streamdeck_gui.deck_service.refresh_cache", lambda url, token: cache)
    settings = AppSettings(
        streamdeck_yaml_path=str(yaml_path),
        ha_url=PLACEHOLDER_HA,
        ha_token="test-token-value",
    )
    with pytest.raises(DeckServiceError, match="Could not read streamdeck.yaml"):
        reject_unknown_entities(settings)
