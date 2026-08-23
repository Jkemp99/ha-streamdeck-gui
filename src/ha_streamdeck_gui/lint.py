"""Semantic checks that go beyond the Pydantic schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ha_streamdeck_gui.decks import DeckModel
from ha_streamdeck_gui.schema import (
    KNOWN_DIAL_EVENT_TYPES,
    StreamDeckConfig,
    collect_page_names,
    iter_buttons,
    pair_dials,
)

Severity = Literal["error", "warning", "info"]


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    path: str


def lint_config(
    config: StreamDeckConfig,
    *,
    deck: DeckModel | None = None,
    known_entities: set[str] | None = None,
    has_includes: bool = False,
) -> list[Issue]:
    issues: list[Issue] = []
    names = collect_page_names(config)
    name_set = set(names)
    anonymous_names = {page.name for page in config.anonymous_pages}

    if len(names) != len(name_set):
        issues.append(
            Issue("warning", "duplicate_page_name", "Two pages share the same name.", "pages"),
        )

    targeted: set[str] = set()
    for page_name, is_anon, index, button in iter_buttons(config):
        kind = "anonymous_pages" if is_anon else "pages"
        loc = f"{kind}.{page_name}.buttons[{index}]"
        if button.special_type == "go-to-page":
            target = button.special_type_data
            if isinstance(target, str):
                targeted.add(target)
                if target not in name_set:
                    issues.append(
                        Issue(
                            "error",
                            "missing_page",
                            f"go-to-page points at {target!r}, which is not a page.",
                            loc,
                        ),
                    )
            elif isinstance(target, int) and target < 0:
                issues.append(
                    Issue("error", "bad_page_index", f"go-to-page index {target} is negative.", loc),
                )
        if known_entities is not None and button.entity_id and "{" not in button.entity_id:
            if button.entity_id not in known_entities:
                issues.append(
                    Issue(
                        "warning",
                        "unknown_entity",
                        f"entity_id {button.entity_id!r} was not in the last Home Assistant fetch.",
                        loc,
                    ),
                )

    for page in config.anonymous_pages:
        if page.name not in targeted:
            issues.append(
                Issue(
                    "warning",
                    "orphan_anonymous_page",
                    f"Anonymous page {page.name!r} is not targeted by any go-to-page button.",
                    f"anonymous_pages.{page.name}",
                ),
            )

    if deck is not None:
        for page in [*config.pages, *config.anonymous_pages]:
            extra = len(page.buttons) - deck.key_count
            if extra > 0:
                issues.append(
                    Issue(
                        "warning",
                        "too_many_buttons",
                        f"Page {page.name!r} has {len(page.buttons)} buttons; "
                        f"{deck.name} only has {deck.key_count} keys.",
                        f"pages.{page.name}.buttons",
                    ),
                )
            paired = pair_dials(page.dials)
            if deck.dial_count and len(paired) > deck.dial_count:
                issues.append(
                    Issue(
                        "warning",
                        "too_many_dials",
                        f"Page {page.name!r} maps to {len(paired)} physical dials; "
                        f"{deck.name} has {deck.dial_count}.",
                        f"pages.{page.name}.dials",
                    ),
                )
            if page.dials and deck.dial_count == 0:
                issues.append(
                    Issue(
                        "warning",
                        "dials_on_key_only_deck",
                        f"Page {page.name!r} has dials, but {deck.name} has no encoders.",
                        f"pages.{page.name}.dials",
                    ),
                )
            for dial_index, dial in enumerate(page.dials):
                event = dial.dial_event_type
                if event and event not in KNOWN_DIAL_EVENT_TYPES:
                    issues.append(
                        Issue(
                            "warning",
                            "unknown_dial_event",
                            f"dial_event_type {event!r} is not TURN or PUSH "
                            "(upstream types this as a free string).",
                            f"pages.{page.name}.dials[{dial_index}]",
                        ),
                    )

    if has_includes:
        issues.append(
            Issue(
                "info",
                "includes_present",
                "This file uses !include. The editor can show a flattened view, "
                "but will not overwrite the modular file unless you save as a new single file.",
                "",
            ),
        )
    return issues
