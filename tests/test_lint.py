from __future__ import annotations

from ha_streamdeck_gui.decks import DECK_MODELS
from ha_streamdeck_gui.lint import lint_config
from ha_streamdeck_gui.schema import Button, Page, StreamDeckConfig


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
