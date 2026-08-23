from __future__ import annotations

import pytest
from pydantic import ValidationError

from ha_streamdeck_gui.schema import (
    SPECIAL_TYPES,
    Button,
    Dial,
    Page,
    StreamDeckConfig,
    flatten_physical_dials,
    pair_dials,
    physical_dials,
)


def test_special_types_match_upstream() -> None:
    assert SPECIAL_TYPES == (
        "next-page",
        "previous-page",
        "empty",
        "go-to-page",
        "close-page",
        "turn-off",
        "light-control",
        "reload",
    )


def test_button_forbids_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        Button(entity_id="light.x", not_a_field=True)  # type: ignore[call-arg]


def test_config_ignores_unknown_keys() -> None:
    config = StreamDeckConfig.model_validate(
        {"pages": [{"name": "Home", "buttons": []}], "custom_extra": 1},
    )
    assert config.pages[0].name == "Home"


def test_defaults() -> None:
    button = Button()
    assert button.text_size == 12
    assert button.text_offset == 0
    assert button.icon_background_color == "#000000"
    assert button.delay == 0.0
    config = StreamDeckConfig(pages=[Page(name="Home")])
    assert config.brightness == 100
    assert config.auto_reload is False
    assert config.long_press_duration == 1.0
    assert config.inactivity_time == -1
    assert config.yaml_encoding == "utf-8"


def test_requires_pages() -> None:
    with pytest.raises(ValidationError):
        StreamDeckConfig(pages=[])


def test_go_to_page_requires_name_or_index() -> None:
    Button(special_type="go-to-page", special_type_data="Kitchen")
    Button(special_type="go-to-page", special_type_data=0)
    with pytest.raises(ValidationError):
        Button(special_type="go-to-page", special_type_data=["nope"])
    with pytest.raises(ValidationError):
        Button(special_type="go-to-page")


def test_special_type_data_forbidden_for_some() -> None:
    for kind in ("next-page", "previous-page", "empty", "turn-off"):
        with pytest.raises(ValidationError):
            Button(special_type=kind, special_type_data="x")


def test_light_control_keys() -> None:
    Button(
        special_type="light-control",
        special_type_data={
            "colors": ["#FF0000"],
            "colormap": "hsv",
            "color_temp_kelvin": [2000],
            "brightnesses": [10, 100],
        },
    )
    with pytest.raises(ValidationError):
        Button(special_type="light-control", special_type_data={"bogus": 1})
    with pytest.raises(ValidationError):
        Button(special_type="light-control", special_type_data={"colors": [1]})


def test_long_press() -> None:
    Button(long_press={"service": "light.turn_off"})
    Button(long_press={"special_type": "next-page"})
    with pytest.raises(ValidationError):
        Button(long_press={"nope": 1})
    with pytest.raises(ValidationError):
        Button(long_press={"special_type_data": "Home"})


def test_dial_pairing_turn_then_push() -> None:
    turn = Dial(entity_id="light.x", dial_event_type="TURN")
    push = Dial(entity_id="light.x", dial_event_type="PUSH")
    extra = Dial(entity_id="media_player.y", dial_event_type="TURN")
    paired = pair_dials([turn, push, extra])
    assert len(paired) == 2
    assert paired[0] == (turn, push)
    assert paired[1] == (extra, None)
    slots = physical_dials([turn, push, extra], slots=4)
    assert slots[0].turn is turn
    assert slots[0].push is push
    assert slots[1].turn is extra
    assert flatten_physical_dials(slots)[0].dial_event_type == "TURN"
    assert flatten_physical_dials(slots)[1].dial_event_type == "PUSH"


def test_color_temp_kelvin_is_not_a_special_type() -> None:
    with pytest.raises(ValidationError):
        Button(special_type="color_temp_kelvin")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Button(special_type="colormap")  # type: ignore[arg-type]
