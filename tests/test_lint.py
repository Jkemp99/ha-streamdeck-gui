from __future__ import annotations

from ha_streamdeck_gui.decks import DECK_MODELS
from ha_streamdeck_gui.lint import lint_config
from ha_streamdeck_gui.schema import Button, Dial, Page, StreamDeckConfig


def test_orphan_and_missing_page() -> None:
    config = StreamDeckConfig(
        pages=[
            Page(
                name="Home",
                buttons=[Button(special_type="go-to-page", special_type_data="missing")],
            ),
        ],
        anonymous_pages=[Page(name="hidden", buttons=[])],
    )
    codes = {issue.code for issue in lint_config(config)}
    assert "missing_page" in codes
    assert "orphan_anonymous_page" in codes


def test_too_many_buttons_for_mini() -> None:
    config = StreamDeckConfig(
        pages=[Page(name="Home", buttons=[Button(special_type="empty")] * 8)],
    )
    issues = lint_config(config, deck=DECK_MODELS["mini"])
    assert any(issue.code == "too_many_buttons" for issue in issues)


def test_unknown_entity_on_dials_and_state() -> None:
    config = StreamDeckConfig(
        state_entity_id="input_boolean.missing",
        pages=[
            Page(
                name="Home",
                buttons=[Button(entity_id="light.real", special_type="empty")],
                dials=[Dial(entity_id="light.kitchen")],
            ),
        ],
    )
    issues = lint_config(config, known_entities={"light.real"})
    paths = {issue.path for issue in issues if issue.code == "unknown_entity"}
    assert "pages.Home.dials[0]" in paths
    assert "state_entity_id" in paths
    assert "pages.Home.buttons[0]" not in paths
