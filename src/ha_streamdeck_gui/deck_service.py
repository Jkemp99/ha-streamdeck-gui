"""Install and start home-assistant-streamdeck-yaml from GUI settings."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from ctypes.util import find_library
from pathlib import Path

from ha_streamdeck_gui.ha import HomeAssistantError, hass_streamdeck_endpoint, refresh_cache
from ha_streamdeck_gui.lint import lint_config
from ha_streamdeck_gui.settings import AppSettings
from ha_streamdeck_gui.yaml_io import load_yaml_file

log = logging.getLogger("ha_streamdeck_gui.deck")

SERVICE_NAME = "home-assistant-streamdeck-yaml"
UNIT_NAME = f"{SERVICE_NAME}.service"
RENDER_APT_PACKAGES = (
    "libcairo2 libpango-1.0-0 libpangocairo-1.0-0 "
    "libgdk-pixbuf-2.0-0 shared-mime-info"
)
CAIRO_SONAMES = ("cairo-2", "cairo", "libcairo.so.2")
CAIRO_PATHS = (
    Path("/usr/lib/aarch64-linux-gnu/libcairo.so.2"),
    Path("/usr/lib/arm-linux-gnueabihf/libcairo.so.2"),
    Path("/usr/lib/x86_64-linux-gnu/libcairo.so.2"),
    Path("/usr/lib/libcairo.so.2"),
)


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


def cairo_library_found() -> bool:
    if any(find_library(name) for name in CAIRO_SONAMES):
        return True
    return any(path.is_file() for path in CAIRO_PATHS)


def require_render_libraries() -> None:
    """Pi OS Lite has no Cairo. Upstream then fails every icon and can ABRT USB."""
    if cairo_library_found():
        return
    raise DeckServiceError(
        "Cairo is not installed, so Stream Deck icons cannot render. On the Pi run: "
        f"sudo apt-get install -y {RENDER_APT_PACKAGES}"
    )


def reject_unknown_entities(settings: AppSettings) -> None:
    """Upstream KeyErrors on missing entity_ids and then resets the hardware."""
    if not settings.ha_url or not settings.ha_token.strip():
        raise DeckServiceError("Set the Home Assistant URL and token in Settings first.")
    try:
        cache = refresh_cache(settings.ha_url, settings.ha_token)
    except HomeAssistantError as exc:
        raise DeckServiceError(
            f"Could not refresh Home Assistant entities before Apply: {exc}"
        ) from exc
    known = {entity.entity_id for entity in cache.entities}
    if not known:
        raise DeckServiceError(
            "Home Assistant returned no entities. Fetch devices, then Apply again."
        )
    yaml_path = Path(settings.streamdeck_yaml_path).expanduser()
    if not yaml_path.is_file():
        raise DeckServiceError(f"YAML file not found: {yaml_path}")
    try:
        loaded = load_yaml_file(yaml_path)
    except Exception as exc:
        raise DeckServiceError(f"Could not read streamdeck.yaml: {exc}") from exc
    unknown = [
        issue
        for issue in lint_config(loaded.config, known_entities=known)
        if issue.code == "unknown_entity"
    ]
    if not unknown:
        return
    names = ", ".join(sorted({issue.entity_id for issue in unknown if issue.entity_id}))
    raise DeckServiceError(
        "These entity_ids are not in Home Assistant and will crash the Stream Deck "
        f"process: {names}. Replace them in the editor, then Apply again."
    )


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


def _package_dir(settings: AppSettings) -> Path:
    python = deck_venv_dir(settings) / "bin" / "python"
    found = subprocess.run(
        [
            str(python),
            "-c",
            "import home_assistant_streamdeck_yaml, pathlib; "
            "print(pathlib.Path(home_assistant_streamdeck_yaml.__file__).parent)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if found.returncode != 0 or not found.stdout.strip():
        raise DeckServiceError("Could not locate the installed home-assistant-streamdeck-yaml package.")
    return Path(found.stdout.strip())


def ensure_deck_assets(settings: AppSettings) -> Path:
    """The PyPI wheel often omits assets/ (font + MDI). Copy them from upstream."""
    root = _package_dir(settings)
    assets = root / "assets"
    font = assets / "Roboto-Regular.ttf"
    if font.is_file():
        return assets
    cache = yaml_dir(settings) / ".upstream-home-assistant-streamdeck-yaml"
    if not (cache / "assets" / "Roboto-Regular.ttf").is_file():
        if cache.exists():
            shutil.rmtree(cache)
        try:
            cloned = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "https://github.com/basnijholt/home-assistant-streamdeck-yaml.git",
                    str(cache),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise DeckServiceError(
                "git is not installed. Install git to download Stream Deck fonts/icons."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DeckServiceError(
                "Timed out downloading Stream Deck fonts/icons. Check network on the Pi."
            ) from exc
        if cloned.returncode != 0 or not (cache / "assets" / "Roboto-Regular.ttf").is_file():
            raise DeckServiceError(
                cloned.stderr.strip()
                or "Could not download Stream Deck fonts/icons. The pip package is missing assets/.",
            )
    try:
        if assets.exists():
            shutil.rmtree(assets)
        shutil.copytree(cache / "assets", assets)
    except OSError as exc:
        raise DeckServiceError(f"Could not copy Stream Deck fonts/icons: {exc}") from exc
    if not font.is_file():
        raise DeckServiceError("Copied assets/ but Roboto-Regular.ttf is still missing.")
    return assets


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
            "StartLimitBurst=3\n"
            "StartLimitIntervalSec=60\n"
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
    _systemctl("reset-failed", SERVICE_NAME)
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


def _status_note(base: str, cairo: bool) -> str:
    if cairo:
        return base
    cairo_note = (
        "Cairo is missing. Icons will not render. On the Pi run: "
        f"sudo apt-get install -y {RENDER_APT_PACKAGES}"
    )
    return f"{base} {cairo_note}"


def service_status() -> dict[str, object]:
    cairo = cairo_library_found()
    if shutil.which("systemctl") is None:
        return {
            "configured": False,
            "running": False,
            "scope": None,
            "cairo": cairo,
            "note": _status_note("systemctl is not available.", cairo),
        }
    active = _systemctl("is-active", SERVICE_NAME)
    show = _systemctl("show", SERVICE_NAME, "--property=ActiveState,SubState,MainPID,FragmentPath")
    logs_text = ""
    if shutil.which("journalctl"):
        logs = subprocess.run(
            ["journalctl", "--user", "-u", SERVICE_NAME, "-n", "40", "--no-pager"],
            check=False,
            capture_output=True,
            text=True,
        )
        logs_text = logs.stdout
    if active.returncode == 0 or "ActiveState" in show.stdout:
        return {
            "configured": True,
            "running": active.stdout.strip() == "active",
            "state": active.stdout.strip(),
            "scope": "user",
            "cairo": cairo,
            "details": show.stdout,
            "logs": logs_text,
            "note": _status_note(
                "The Stream Deck process reads streamdeck.yaml. Keep auto_reload: true.",
                cairo,
            ),
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
            "cairo": cairo,
            "note": _status_note("A system unit is already running.", cairo),
        }
    return {
        "configured": False,
        "running": False,
        "state": active.stdout.strip() or "inactive",
        "scope": "user",
        "cairo": cairo,
        "logs": logs_text,
        "note": _status_note(
            "The Stream Deck service is not running. Use Settings → Apply to Stream Deck.",
            cairo,
        ),
    }


def apply_from_settings(settings: AppSettings) -> dict[str, object]:
    require_render_libraries()
    reject_unknown_entities(settings)
    env_path = write_deck_env(settings)
    binary = ensure_deck_package(settings)
    assets = ensure_deck_assets(settings)
    unit = write_user_unit(settings)
    start_user_service()
    status = service_status()
    status.update(
        {
            "ok": True,
            "deck_env": str(env_path),
            "binary": str(binary),
            "assets": str(assets),
            "unit": str(unit),
        },
    )
    return status
