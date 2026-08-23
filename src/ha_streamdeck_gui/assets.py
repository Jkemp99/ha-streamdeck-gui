"""Custom icon files for the `icon` field.

Upstream loads a bare filename from its own assets directory, or any absolute
path. Uploads land in a user-configured folder (default: next to streamdeck.yaml).
The YAML stores an absolute path so the Stream Deck service can find the file
without copying it into site-packages.
"""

from __future__ import annotations

import re
from pathlib import Path

from ha_streamdeck_gui.settings import AppSettings

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
MAX_BYTES = 5 * 1024 * 1024
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class AssetsError(RuntimeError):
    pass


def resolve_assets_dir(settings: AppSettings) -> Path:
    if settings.assets_dir:
        return Path(settings.assets_dir).expanduser()
    if settings.streamdeck_yaml_path:
        return Path(settings.streamdeck_yaml_path).expanduser().parent / "assets"
    raise AssetsError(
        "No assets directory. Set one in Settings, or set the streamdeck.yaml path "
        "(uploads then go to <yaml-dir>/assets).",
    )


def safe_filename(name: str) -> str:
    base = Path(name).name
    if base in {"", ".", ".."}:
        raise AssetsError("Invalid file name.")
    cleaned = SAFE_NAME.sub("_", base)
    suffix = Path(cleaned).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise AssetsError(f"Unsupported type {suffix or '(none)'}. Use {sorted(ALLOWED_SUFFIXES)}.")
    if cleaned.startswith("."):
        raise AssetsError("Invalid file name.")
    return cleaned


def asset_path(root: Path, name: str) -> Path:
    root_resolved = root.expanduser().resolve()
    candidate = (root_resolved / safe_filename(name)).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise AssetsError("Path escapes the assets directory.") from exc
    return candidate


def list_assets(root: Path) -> list[dict[str, str]]:
    if not root.is_dir():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        items.append(
            {
                "name": path.name,
                "path": str(path.resolve()),
                "preview": f"/api/assets/{path.name}",
            },
        )
    return items


def save_asset(root: Path, filename: str, data: bytes) -> dict[str, str]:
    if len(data) > MAX_BYTES:
        raise AssetsError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise AssetsError("Empty file.")
    root.mkdir(parents=True, exist_ok=True)
    dest = asset_path(root, filename)
    dest.write_bytes(data)
    return {
        "name": dest.name,
        "path": str(dest),
        "preview": f"/api/assets/{dest.name}",
    }
