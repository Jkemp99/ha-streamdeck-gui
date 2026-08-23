from __future__ import annotations

from pathlib import Path

from ha_streamdeck_gui.deck_service import write_deck_env
from ha_streamdeck_gui.ha import hass_streamdeck_endpoint
from ha_streamdeck_gui.settings import AppSettings


def test_http_url_puts_port_on_host() -> None:
    host, protocol = hass_streamdeck_endpoint("http://192.168.4.62:8123")
    assert host == "192.168.4.62:8123"
    assert protocol == "ws"


def test_http_url_defaults_to_8123() -> None:
    host, protocol = hass_streamdeck_endpoint("http://192.168.4.62")
    assert host == "192.168.4.62:8123"
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
        ha_url="http://192.168.4.62:8123",
        ha_token="test-token-value",
    )
    env_path = write_deck_env(settings)
    text = env_path.read_text(encoding="utf-8")
    assert "HASS_HOST=192.168.4.62:8123" in text
    assert "HASS_TOKEN=test-token-value" in text
    assert f"STREAMDECK_CONFIG={yaml_path.resolve()}" in text
    assert "WEBSOCKET_PROTOCOL=ws" in text
    assert env_path.stat().st_mode & 0o777 == 0o600
