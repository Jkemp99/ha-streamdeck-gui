"""Pydantic models mirroring basnijholt/home-assistant-streamdeck-yaml.

Field names, types, defaults, extra-field policy, and special_type validation
are taken from home_assistant_streamdeck_yaml.py (Config, Page, Button, Dial).
If this file and upstream disagree, upstream wins.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SpecialType = Literal[
    "next-page",
    "previous-page",
    "empty",
    "go-to-page",
    "close-page",
    "turn-off",
    "light-control",
    "reload",
]

SPECIAL_TYPES: tuple[str, ...] = get_args(SpecialType)

# Upstream forbids special_type_data for these four only.
# close-page and reload are not in this set.
SPECIAL_TYPES_WITHOUT_DATA = frozenset(
    {"next-page", "previous-page", "empty", "turn-off"},
)

LIGHT_CONTROL_KEYS = frozenset({"colors", "colormap", "color_temp_kelvin", "brightnesses"})
LONG_PRESS_KEYS = frozenset(
    {
        "service",
        "service_data",
        "entity_id",
        "target",
        "special_type",
        "special_type_data",
    },
)

BUTTON_DIAL_TEMPLATABLE = frozenset(
    {
        "entity_id",
        "linked_entity",
        "service",
        "service_data",
        "target",
        "text",
        "text_color",
        "icon",
        "icon_mdi",
        "icon_background_color",
        "icon_mdi_color",
        "delay",
    },
)
BUTTON_TEMPLATABLE = BUTTON_DIAL_TEMPLATABLE | {"special_type_data", "long_press"}
DIAL_TEMPLATABLE = BUTTON_DIAL_TEMPLATABLE | {
    "dial_event_type",
    "state_attribute",
    "attributes",
    "allow_touchscreen_events",
}

# Documented runtime values. Upstream types this as str | None, not a Literal.
KNOWN_DIAL_EVENT_TYPES = frozenset({"TURN", "PUSH"})


def validate_special_type_data(special_type: str | None, value: Any) -> Any:
    """Reproduce Button._validate_special_type_data from upstream."""
    if special_type == "go-to-page" and not isinstance(value, (int, str)):
        raise ValueError("If special_type is go-to-page, special_type_data must be an int or str")
    if special_type in SPECIAL_TYPES_WITHOUT_DATA and value is not None:
        raise ValueError(f"special_type_data needs to be empty with special_type={special_type!r}")

    if special_type == "light-control":
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ValueError(
                f"With 'light-control', 'special_type_data' must be a dict, not '{value}'",
            )
        invalid = set(value) - LIGHT_CONTROL_KEYS
        if invalid:
            raise ValueError(
                f"Invalid keys in 'special_type_data', only {set(LIGHT_CONTROL_KEYS)} allowed",
            )
        if "colors" in value:
            colors = value["colors"]
            if not isinstance(colors, (tuple, list)):
                raise ValueError("If 'colors' is present, it must be a list")
            if any(not isinstance(color, str) for color in colors):
                raise ValueError("All colors must be strings")
            value["colors"] = list(colors)
        if "color_temp_kelvin" in value:
            kelvins = value["color_temp_kelvin"]
            if any(not isinstance(kelvin, int) or isinstance(kelvin, bool) for kelvin in kelvins):
                raise ValueError("All color_temp_kelvin must be integers")
            value["color_temp_kelvin"] = list(kelvins)
        if "brightnesses" in value:
            brightnesses = value["brightnesses"]
            if any(not isinstance(item, int) or isinstance(item, bool) for item in brightnesses):
                raise ValueError("All brightnesses must be integers")
            value["brightnesses"] = list(brightnesses)
    return value


def validate_long_press(value: Any) -> Any:
    """Reproduce Button._validate_long_press from upstream."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("long_press must be a dictionary")
    invalid = set(value) - LONG_PRESS_KEYS
    if invalid:
        raise ValueError(f"Invalid keys in long_press: {invalid}. Allowed: {set(LONG_PRESS_KEYS)}")
    if "service" in value and not isinstance(value["service"], str):
        raise ValueError("long_press.service must be a string")
    if "service_data" in value and not isinstance(value["service_data"], dict):
        raise ValueError("long_press.service_data must be a dictionary")
    if "entity_id" in value and not isinstance(value["entity_id"], str):
        raise ValueError("long_press.entity_id must be a string")
    if "target" in value and not isinstance(value["target"], dict):
        raise ValueError("long_press.target must be a dictionary")
    if "special_type" in value:
        if value["special_type"] not in SPECIAL_TYPES:
            raise ValueError(
                f"long_press.special_type must be one of {SPECIAL_TYPES} "
                f"(got {value['special_type']})",
            )
    if "special_type_data" in value and "special_type" not in value:
        raise ValueError("long_press.special_type_data requires special_type to be set")
    if "special_type" in value and "special_type_data" in value:
        validate_special_type_data(value["special_type"], value["special_type_data"])
    return value


class ButtonDialBase(BaseModel):
    """Shared fields of Button and Dial (_ButtonDialBase in upstream)."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(
        default=None,
        description="The entity_id that this control targets. Re-renders when state changes.",
    )
    linked_entity: str | None = Field(
        default=None,
        description="A secondary entity_id used for updating images and states.",
    )
    service: str | None = Field(
        default=None,
        description="The Home Assistant service called when this control is used.",
    )
    service_data: dict[str, Any] | None = Field(
        default=None,
        description="Data passed to the service. If empty, entity_id is passed.",
    )
    target: dict[str, Any] | None = Field(
        default=None,
        description="Target passed to the service call.",
    )
    text: str | None = Field(
        default=None,
        description="Text drawn on the key (or above a dial). Use \\n or a YAML block scalar.",
    )
    text_color: str | None = Field(
        default=None,
        description=(
            "Text color. Default is white, or amber/white from entity on/off when entity_id is set."
        ),
    )
    text_size: int = Field(default=12, description="Integer text size.")
    text_offset: int = Field(
        default=0,
        description="Pixels to move text up (positive) or down (negative) from center.",
    )
    icon: str | None = Field(
        default=None,
        description=(
            "Image filename (absolute, or relative to the assets directory), "
            "'url:https://…', 'spotify:…', or 'ring:25'."
        ),
    )
    icon_mdi: str | None = Field(
        default=None,
        description="Material Design Icon name. SVG is downloaded and cached by upstream.",
    )
    icon_background_color: str = Field(
        default="#000000",
        description="Hex background color used when no `icon` image is specified.",
    )
    icon_mdi_color: str | None = Field(
        default=None,
        description="Hex color for the MDI icon. Defaults to a desaturated text_color.",
    )
    icon_gray_when_off: bool = Field(
        default=False,
        description="If icon and entity_id are set, grayscale the icon when the entity is off.",
    )
    delay: float | str = Field(
        default=0.0,
        description="Seconds to wait before calling the service. Float or a template string.",
    )


class Button(ButtonDialBase):
    """One Stream Deck key. extra='forbid' matches upstream."""

    special_type: SpecialType | None = Field(
        default=None,
        description=(
            "Special button behavior. None is a normal service button. "
            "Valid values: next-page, previous-page, empty, go-to-page, "
            "close-page, turn-off, light-control, reload."
        ),
    )
    special_type_data: Any | None = Field(
        default=None,
        validate_default=True,
        description=(
            "Payload for special_type. go-to-page: page name (str) or index (int). "
            "light-control: optional dict with colors, colormap, color_temp_kelvin, brightnesses."
        ),
    )
    long_press: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Alternate action after long_press_duration. Allowed keys: service, "
            "service_data, entity_id, target, special_type, special_type_data."
        ),
    )

    @field_validator("special_type_data")
    @classmethod
    def _check_special_type_data(cls, value: Any, info: Any) -> Any:
        return validate_special_type_data(info.data.get("special_type"), value)

    @field_validator("long_press")
    @classmethod
    def _check_long_press(cls, value: Any) -> Any:
        return validate_long_press(value)


class Dial(ButtonDialBase):
    """One Stream Deck + dial action. extra='forbid' matches upstream.

    A physical dial can have two Dial entries (TURN and PUSH). Upstream pairs
    consecutive entries whose dial_event_type values differ.
    """

    dial_event_type: str | None = Field(
        default=None,
        description="Event that triggers the service. Upstream examples use TURN or PUSH.",
    )
    state_attribute: str | None = Field(
        default=None,
        description="Entity attribute used as the dial's numeric state (e.g. brightness).",
    )
    attributes: dict[str, float] | None = Field(
        default=None,
        description="Dial range: min, max, and step. Internal defaults are 0 / 100 / 1.",
    )
    allow_touchscreen_events: bool = Field(
        default=False,
        description=(
            "If true, a short tap on this dial's touch-strip segment sets min "
            "and a long press sets max."
        ),
    )


class Page(BaseModel):
    """One page of buttons (and optional dials). Extra keys are ignored, like upstream."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="The name of the page.")
    buttons: list[Button] = Field(default_factory=list, description="Buttons on the page.")
    dials: list[Dial] = Field(default_factory=list, description="Dials on the page (Stream Deck +).")


class StreamDeckConfig(BaseModel):
    """Top-level streamdeck.yaml document. Extra keys are ignored, like upstream."""

    model_config = ConfigDict(extra="ignore")

    yaml_encoding: str | None = Field(
        default="utf-8",
        description="The encoding of the YAML file.",
    )
    pages: list[Page] = Field(default_factory=list, description="Visible pages, in cycle order.")
    anonymous_pages: list[Page] = Field(
        default_factory=list,
        description=(
            "Hidden pages reachable only via special_type: go-to-page. "
            "After a button click they return to the previous page."
        ),
    )
    state_entity_id: str | None = Field(
        default=None,
        description="Entity that syncs whether the deck display is on.",
    )
    brightness: int = Field(default=100, description="Default brightness 0–100.")
    brightness_entity_id: str | None = Field(
        default=None,
        description="Entity that syncs brightness 0–100.",
    )
    auto_reload: bool = Field(
        default=False,
        description="If true, upstream reloads YAML when the file changes.",
    )
    long_press_duration: float = Field(
        default=1.0,
        description="Seconds a key must be held to fire long_press.",
    )
    inactivity_time: float = Field(
        default=-1,
        description="Seconds of idle time before the deck turns off. -1 disables.",
    )

    @model_validator(mode="after")
    def _require_pages(self) -> StreamDeckConfig:
        if not self.pages:
            raise ValueError("No pages defined. Add at least one page with buttons.")
        return self


class PhysicalDial(BaseModel):
    """One hardware encoder: optional TURN and/or PUSH actions."""

    turn: Dial | None = None
    push: Dial | None = None


def pair_dials(dials: list[Dial]) -> list[tuple[Dial, Dial | None]]:
    """Match Page.sort_dials: pair consecutive dials with different event types."""
    paired: list[tuple[Dial, Dial | None]] = []
    skip = False
    for index, dial in enumerate(dials):
        if skip:
            skip = False
            continue
        if index + 1 < len(dials):
            nxt = dials[index + 1]
            if dial.dial_event_type != nxt.dial_event_type:
                paired.append((dial, nxt))
                skip = True
                continue
        paired.append((dial, None))
    return paired


def physical_dials(dials: list[Dial], slots: int = 4) -> list[PhysicalDial]:
    """Group YAML dial entries into hardware encoder slots."""
    result = [PhysicalDial() for _ in range(slots)]
    for slot_index, (first, second) in enumerate(pair_dials(dials)):
        if slot_index >= slots:
            break
        for candidate in (first, second):
            if candidate is None:
                continue
            event = (candidate.dial_event_type or "").upper()
            if event == "PUSH" and result[slot_index].push is None:
                result[slot_index].push = candidate
            else:
                result[slot_index].turn = candidate
    return result


def flatten_physical_dials(slots: list[PhysicalDial]) -> list[Dial]:
    """Write hardware slots back to the upstream flat list (TURN then PUSH)."""
    out: list[Dial] = []
    for slot in slots:
        if slot.turn is not None:
            data = slot.turn.model_dump()
            data["dial_event_type"] = slot.turn.dial_event_type or "TURN"
            out.append(Dial.model_validate(data))
        if slot.push is not None:
            data = slot.push.model_dump()
            data["dial_event_type"] = slot.push.dial_event_type or "PUSH"
            out.append(Dial.model_validate(data))
    return out


def collect_page_names(config: StreamDeckConfig) -> list[str]:
    return [page.name for page in config.pages] + [page.name for page in config.anonymous_pages]


def iter_buttons(config: StreamDeckConfig) -> list[tuple[str, bool, int, Button]]:
    """Yield (page_name, is_anonymous, index, button)."""
    found: list[tuple[str, bool, int, Button]] = []
    for page in config.pages:
        for index, button in enumerate(page.buttons):
            found.append((page.name, False, index, button))
    for page in config.anonymous_pages:
        for index, button in enumerate(page.buttons):
            found.append((page.name, True, index, button))
    return found


def config_to_dump_dict(config: StreamDeckConfig) -> dict[str, Any]:
    """Serialize for YAML, omitting unset defaults so files stay hand-editable."""
    return config.model_dump(exclude_unset=True, exclude_none=False)
