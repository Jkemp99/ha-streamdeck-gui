from __future__ import annotations

from pathlib import Path

import pytest

from ha_streamdeck_gui.sample import build_sample_config, sample_yaml
from ha_streamdeck_gui.yaml_io import (
    IncludeProtectedError,
    detect_includes,
    dump_config_yaml,
    list_backups,
    load_yaml_file,
    parse_yaml_text,
    save_yaml_file,
)

COMMENTED = """\
# keep this comment
brightness: 80  # readable
auto_reload: true
pages:
  - name: Home  # landing
    buttons:
      - entity_id: light.kitchen
        service: light.toggle
        icon_mdi: lightbulb
"""


def test_roundtrip_preserves_comments() -> None:
    loaded = parse_yaml_text(COMMENTED)
    out = loaded.text
    assert "keep this comment" in out
    assert "landing" in out
    dumped = dump_config_yaml(loaded.config)
    reloaded = parse_yaml_text(dumped)
    assert reloaded.config.brightness == 80
    assert reloaded.config.pages[0].buttons[0].entity_id == "light.kitchen"


def test_save_without_edit_keeps_original_text(tmp_path: Path) -> None:
    path = tmp_path / "streamdeck.yaml"
    path.write_text(COMMENTED, encoding="utf-8")
    loaded = load_yaml_file(path)
    save_yaml_file(path, config=loaded.config, original=loaded, backup_count=3)
    assert path.read_text(encoding="utf-8") == COMMENTED
    backups = list_backups(path)
    assert backups


def test_backup_before_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "streamdeck.yaml"
    path.write_text(COMMENTED, encoding="utf-8")
    loaded = load_yaml_file(path)
    loaded.config.brightness = 40
    save_yaml_file(path, config=loaded.config, original=loaded, backup_count=2)
    backups = list_backups(path)
    assert len(backups) == 1
    assert "brightness: 80" in Path(backups[0]["path"]).read_text(encoding="utf-8")


def test_refuses_to_overwrite_includes(tmp_path: Path) -> None:
    path = tmp_path / "streamdeck.yaml"
    path.write_text("pages:\n  - name: Home\n    buttons: !include home.yaml\n", encoding="utf-8")
    with pytest.raises(IncludeProtectedError):
        save_yaml_file(path, text=sample_yaml(), allow_inline_includes=False)


def test_detect_includes() -> None:
    assert detect_includes("buttons: !include includes/home.yaml")
    assert not detect_includes("text: include me")


def test_sample_validates() -> None:
    config = build_sample_config()
    assert len(config.pages) >= 2
    assert config.anonymous_pages
    assert any(page.dials for page in config.pages)
    reloaded = parse_yaml_text(sample_yaml())
    assert reloaded.config.pages[0].name == "Home"
    assert reloaded.config.pages[0].dials[0].dial_event_type == "TURN"
    assert reloaded.config.pages[0].dials[1].dial_event_type == "PUSH"
