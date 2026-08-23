"""Stream Deck geometries used by the visual editor.

Counts come from python-elgato-streamdeck device classes, which is the same
library upstream home-assistant-streamdeck-yaml uses. The YAML schema itself
has no deck-model field — layout is inferred from the live device at runtime.
This GUI lets the user pick a model so the grid can be drawn without USB access.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DeckModelId = Literal["mini", "original", "mk2", "xl", "plus", "neo"]


class DeckModel(BaseModel):
    id: DeckModelId
    name: str
    rows: int
    cols: int
    key_count: int
    dial_count: int = 0
    touch_key_count: int = 0
    has_touchscreen: bool = False
    has_info_screen: bool = False
    notes: str = ""


# Geometries from python-elgato-streamdeck device classes.
DECK_MODELS: dict[DeckModelId, DeckModel] = {
    "mini": DeckModel(
        id="mini",
        name="Stream Deck Mini",
        rows=2,
        cols=3,
        key_count=6,
    ),
    "original": DeckModel(
        id="original",
        name="Stream Deck Original",
        rows=3,
        cols=5,
        key_count=15,
    ),
    "mk2": DeckModel(
        id="mk2",
        name="Stream Deck MK.2",
        rows=3,
        cols=5,
        key_count=15,
        notes="Same 3×5 layout as the Original.",
    ),
    "xl": DeckModel(
        id="xl",
        name="Stream Deck XL",
        rows=4,
        cols=8,
        key_count=32,
    ),
    "plus": DeckModel(
        id="plus",
        name="Stream Deck +",
        rows=2,
        cols=4,
        key_count=8,
        dial_count=4,
        has_touchscreen=True,
        notes=(
            "The touch strip is the LCD above the four dials. Upstream does not "
            "give it its own YAML object — each Dial renders onto one quarter of "
            "the strip. Swipe left/right changes pages. TURN and PUSH for the "
            "same physical dial are two consecutive Dial entries with different "
            "dial_event_type values."
        ),
    ),
    "neo": DeckModel(
        id="neo",
        name="Stream Deck Neo",
        rows=2,
        cols=4,
        key_count=8,
        touch_key_count=2,
        has_info_screen=True,
        notes=(
            "python-elgato-streamdeck supports Neo (8 LCD keys + 2 color touch "
            "keys + 248×58 info screen). Upstream YAML only maps buttons to "
            "KEY_COUNT (the 8 LCD keys). The touch keys and info screen are not "
            "configurable in streamdeck.yaml."
        ),
    ),
}


def get_deck_model(model_id: DeckModelId | str | None) -> DeckModel | None:
    if model_id is None:
        return None
    return DECK_MODELS.get(model_id)  # type: ignore[arg-type]


def list_deck_models() -> list[DeckModel]:
    return list(DECK_MODELS.values())


class DeckHint(BaseModel):
    """Optional user-selected model used only by this GUI."""

    model: DeckModelId | None = Field(
        default=None,
        description="User-selected deck model. Not part of streamdeck.yaml.",
    )
