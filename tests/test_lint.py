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
    unknown = [issue for issue in issues if issue.code == "unknown_entity"]
    paths = {issue.path for issue in unknown}
    assert "pages.Home.dials[0]" in paths
    assert "state_entity_id" in paths
    assert "pages.Home.buttons[0]" not in paths
    assert all(issue.severity == "error" for issue in unknown)


def test_toggle_on_brightness_dial_warns() -> None:
    config = StreamDeckConfig(
        pages=[
            Page(
                name="Home",
                dials=[
                    Dial(
                        entity_id="light.office",
                        service="light.toggle",
                        service_data={"brightness": "{{ dial_value() | int }}"},
                        dial_event_type="TURN",
                        state_attribute="brightness",
                    ),
                    Dial(
                        entity_id="light.office",
                        service="light.toggle",
                        dial_event_type="PUSH",
                    ),
                ],
            ),
        ],
    )
    issues = [issue for issue in lint_config(config) if issue.code == "toggle_on_dimmer"]
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].path == "pages.Home.dials[0]"


def test_empty_known_set_flags_every_entity() -> None:
    config = StreamDeckConfig(
        pages=[Page(name="Home", buttons=[Button(entity_id="light.real")])],
    )
    issues = lint_config(config, known_entities=set())
    assert any(issue.code == "unknown_entity" and issue.severity == "error" for issue in issues)
