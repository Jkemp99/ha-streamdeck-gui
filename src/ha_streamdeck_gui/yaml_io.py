"""Load and save streamdeck.yaml with comment-preserving ruamel.yaml."""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ha_streamdeck_gui.schema import StreamDeckConfig

INCLUDE_RE = re.compile(r"(^|[ \t])!include\b")

CONFIG_KEY_ORDER = (
    "yaml_encoding",
    "brightness",
    "brightness_entity_id",
    "auto_reload",
    "state_entity_id",
    "long_press_duration",
    "inactivity_time",
    "pages",
    "anonymous_pages",
)
PAGE_KEY_ORDER = ("name", "buttons", "dials")


class IncludeProtectedError(RuntimeError):
    """Raised when a save would overwrite a file that uses !include."""


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 120
    return yaml


def detect_includes(text: str) -> bool:
    return bool(INCLUDE_RE.search(text))


def included_paths(text: str, root: Path) -> list[str]:
    paths: list[str] = []
    for match in re.finditer(r"!include\s+(\S+)", text):
        raw = match.group(1).strip().strip("'\"")
        if raw.startswith("{"):
            continue
        paths.append(str((root / raw).resolve()) if not Path(raw).is_absolute() else raw)
    return paths


@dataclass
class LoadedConfig:
    path: Path | None
    text: str
    data: Any
    config: StreamDeckConfig
    has_includes: bool
    include_paths: list[str] = field(default_factory=list)


def parse_yaml_text(text: str, *, path: Path | None = None) -> LoadedConfig:
    has_includes = detect_includes(text)
    include_paths = included_paths(text, path.parent if path else Path.cwd())
    yaml = _yaml()
    data = yaml.load(text) or CommentedMap()
    if has_includes:
        # !include tags that ruamel did not resolve become tagged nodes or None.
        # Flatten using a simple recursive resolver for display/validation.
        data = _resolve_includes(data, path.parent if path else Path.cwd())
    config = StreamDeckConfig.model_validate(_to_plain(data))
    return LoadedConfig(
        path=path,
        text=text,
        data=data,
        config=config,
        has_includes=has_includes,
        include_paths=include_paths,
    )


def load_yaml_file(path: Path) -> LoadedConfig:
    text = path.read_text(encoding="utf-8")
    return parse_yaml_text(text, path=path)


def dump_config_yaml(config: StreamDeckConfig) -> str:
    payload = _ordered_config(config.model_dump(exclude_unset=True, exclude_defaults=False))
    stream = StringIO()
    _yaml().dump(payload, stream)
    return stream.getvalue()


def dump_raw_yaml(data: Any) -> str:
    stream = StringIO()
    _yaml().dump(data, stream)
    return stream.getvalue()


def save_yaml_file(
    path: Path,
    *,
    text: str | None = None,
    config: StreamDeckConfig | None = None,
    backup_count: int = 10,
    allow_inline_includes: bool = False,
    original: LoadedConfig | None = None,
) -> Path | None:
    """Write YAML. Returns the backup path if a backup was created."""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if detect_includes(existing) and not allow_inline_includes:
            raise IncludeProtectedError(
                f"{path} uses !include. Refusing to overwrite a modular config. "
                "Save as a new single file, or set allow_inline_includes after review.",
            )

    if text is None:
        if config is None:
            raise ValueError("Provide text or config to save")
        if original is not None and not original.has_includes:
            if config.model_dump() == original.config.model_dump():
                text = original.text
            else:
                text = dump_config_yaml(config)
        else:
            text = dump_config_yaml(config)

    backup_path = None
    if path.exists():
        backup_path = write_backup(path, keep=backup_count)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return backup_path


def backup_dir_for(path: Path) -> Path:
    return path.parent / ".ha-streamdeck-gui-backups"


def write_backup(path: Path, *, keep: int = 10) -> Path:
    folder = backup_dir_for(path)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = folder / f"{path.name}.{stamp}.yaml"
    shutil.copy2(path, dest)
    _prune_backups(folder, path.name, keep=keep)
    return dest


def list_backups(path: Path) -> list[dict[str, str]]:
    folder = backup_dir_for(path)
    if not folder.is_dir():
        return []
    items: list[dict[str, str]] = []
    for candidate in sorted(folder.glob(f"{path.name}.*.yaml"), reverse=True):
        items.append(
            {
                "name": candidate.name,
                "path": str(candidate),
                "modified": datetime.fromtimestamp(
                    candidate.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat(),
            },
        )
    return items


def restore_backup(backup: Path, dest: Path, *, backup_count: int = 10) -> Path | None:
    prior = write_backup(dest, keep=backup_count) if dest.exists() else None
    shutil.copy2(backup, dest)
    return prior


def _prune_backups(folder: Path, stem: str, *, keep: int) -> None:
    matches = sorted(folder.glob(f"{stem}.*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)
    for extra in matches[keep:]:
        extra.unlink(missing_ok=True)


def yaml_diff(old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="current",
            tofile="proposed",
        ),
    )


def _resolve_includes(node: Any, root: Path) -> Any:
    if isinstance(node, dict):
        return {key: _resolve_includes(value, root) for key, value in node.items()}
    if isinstance(node, list):
        out: list[Any] = []
        for item in node:
            resolved = _resolve_includes(item, root)
            if isinstance(resolved, list):
                out.extend(resolved)
            else:
                out.append(resolved)
        return out
    return node


def _to_plain(node: Any) -> Any:
    if isinstance(node, dict):
        return {str(key): _to_plain(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_to_plain(item) for item in node]
    return node


def _ordered_config(data: dict[str, Any]) -> CommentedMap:
    ordered = CommentedMap()
    for key in CONFIG_KEY_ORDER:
        if key in data:
            if key in {"pages", "anonymous_pages"}:
                ordered[key] = _ordered_pages(data[key])
            else:
                ordered[key] = data[key]
    for key, value in data.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _ordered_pages(pages: list[dict[str, Any]]) -> CommentedSeq:
    seq = CommentedSeq()
    for page in pages:
        item = CommentedMap()
        for key in PAGE_KEY_ORDER:
            if key in page:
                item[key] = page[key]
        for key, value in page.items():
            if key not in item:
                item[key] = value
        seq.append(item)
    return seq
