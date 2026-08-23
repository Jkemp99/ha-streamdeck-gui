"""Install and start home-assistant-streamdeck-yaml from GUI settings."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ha_streamdeck_gui.ha import hass_streamdeck_endpoint
from ha_streamdeck_gui.settings import AppSettings

log = logging.getLogger("ha_streamdeck_gui.deck")

SERVICE_NAME = "home-assistant-streamdeck-yaml"
UNIT_NAME = f"{SERVICE_NAME}.service"


class DeckServiceError(RuntimeError):
    pass


def yaml_dir(settings: AppSettings) -> Path:
    if not settings.streamdeck_yaml_path:
        raise DeckServiceError("Set the streamdeck.yaml path in Settings first.")
    return Path(settings.streamdeck_yaml_path).expanduser().resolve().parent


def deck_env_path(settings: AppSettings) -> Path:
    return yaml_dir(settings) / "deck.env"


def deck_venv_dir(settings: AppSettings) -> Path:
    return yaml_dir(settings) / ".venv-deck"


def deck_binary(settings: AppSettings) -> Path:
    return deck_venv_dir(settings) / "bin" / "home-assistant-streamdeck-yaml"


def user_unit_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "systemd" / "user" / UNIT_NAME


def write_deck_env(settings: AppSettings) -> Path:
    if not settings.ha_url:
        raise DeckServiceError("Set the Home Assistant URL in Settings first.")
    if not settings.ha_token.strip():
        raise DeckServiceError("Set the Home Assistant token in Settings first.")
    host, protocol = hass_streamdeck_endpoint(settings.ha_url)
    yaml_path = Path(settings.streamdeck_yaml_path).expanduser().resolve()
    path = deck_env_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"HASS_HOST={host}\n"
        f"HASS_TOKEN={settings.ha_token.strip()}\n"
        f"STREAMDECK_CONFIG={yaml_path}\n"
        f"WEBSOCKET_PROTOCOL={protocol}\n"
    )
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return path


def ensure_deck_package(settings: AppSettings) -> Path:
    binary = deck_binary(settings)
    if binary.is_file():
        return binary
    venv = deck_venv_dir(settings)
    log.info("Creating Stream Deck venv at %s", venv)
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        raise DeckServiceError(created.stderr.strip() or "Could not create the Stream Deck virtualenv.")
    pip = venv / "bin" / "pip"
    installed = subprocess.run(
        [str(pip), "install", "--upgrade", "pip", "home-assistant-streamdeck-yaml"],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if installed.returncode != 0 or not binary.is_file():
        raise DeckServiceError(
            installed.stderr.strip()
            or "Could not install home-assistant-streamdeck-yaml. Check network on the Pi.",
        )
    return binary


def write_user_unit(settings: AppSettings) -> Path:
    binary = deck_binary(settings)
    env_file = deck_env_path(settings)
    path = user_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "[Unit]\n"
            "Description=Home Assistant Stream Deck YAML\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={yaml_dir(settings)}\n"
            f"EnvironmentFile={env_file}\n"
            f"ExecStart={binary}\n"
            "Restart=on-failure\n"
            "RestartSec=5\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        ),
        encoding="utf-8",
    )
    return path


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def start_user_service() -> None:
    if shutil.which("systemctl") is None:
        raise DeckServiceError("systemctl is not available on this machine.")
    reloaded = _systemctl("daemon-reload")
    if reloaded.returncode != 0:
        raise DeckServiceError(reloaded.stderr.strip() or "systemctl --user daemon-reload failed")
    started = _systemctl("enable", "--now", SERVICE_NAME)
    if started.returncode != 0:
        fallback = _systemctl("restart", SERVICE_NAME)
        if fallback.returncode != 0:
            raise DeckServiceError(
                (started.stderr or fallback.stderr or started.stdout or fallback.stdout).strip()
                or "Could not start the Stream Deck user service.",
            )


def service_status() -> dict[str, object]:
    if shutil.which("systemctl") is None:
        return {
            "configured": False,
            "running": False,
            "scope": None,
            "note": "systemctl is not available.",
        }
    active = _systemctl("is-active", SERVICE_NAME)
    show = _systemctl("show", SERVICE_NAME, "--property=ActiveState,SubState,MainPID,FragmentPath")
    logs = _systemctl("status", SERVICE_NAME, "--no-pager", "-n", "20")
    if active.returncode == 0 or "ActiveState" in show.stdout:
        return {
            "configured": True,
            "running": active.stdout.strip() == "active",
            "state": active.stdout.strip(),
            "scope": "user",
            "details": show.stdout,
            "logs": logs.stdout,
            "note": "The Stream Deck process reads streamdeck.yaml. Keep auto_reload: true.",
        }
    system = subprocess.run(
        ["systemctl", "is-active", SERVICE_NAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if system.stdout.strip() == "active":
        return {
            "configured": True,
            "running": True,
            "state": "active",
            "scope": "system",
            "note": "A system unit is already running.",
        }
    return {
        "configured": False,
        "running": False,
        "state": active.stdout.strip() or "inactive",
        "scope": "user",
        "logs": logs.stdout,
        "note": "The Stream Deck service is not running. Use Settings → Apply to Stream Deck.",
    }


def apply_from_settings(settings: AppSettings) -> dict[str, object]:
    env_path = write_deck_env(settings)
    binary = ensure_deck_package(settings)
    unit = write_user_unit(settings)
    start_user_service()
    status = service_status()
    status.update(
        {
            "ok": True,
            "deck_env": str(env_path),
            "binary": str(binary),
            "unit": str(unit),
        },
    )
    return status
