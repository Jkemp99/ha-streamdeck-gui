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
    entity_id: str | None = None


def _unknown_entity(entity_id: str | None, path: str, known_entities: set[str] | None) -> Issue | None:
    if known_entities is None or not entity_id or "{" in entity_id:
        return None
    if entity_id in known_entities:
        return None
    return Issue(
        "error",
        "unknown_entity",
        f"entity_id {entity_id!r} is not in Home Assistant and will crash the Stream Deck.",
        path,
        entity_id=entity_id,
    )


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
        unknown = _unknown_entity(button.entity_id, loc, known_entities)
        if unknown:
            issues.append(unknown)

    for page_name, is_anon, page in (
        *((page.name, False, page) for page in config.pages),
        *((page.name, True, page) for page in config.anonymous_pages),
    ):
        kind = "anonymous_pages" if is_anon else "pages"
        for dial_index, dial in enumerate(page.dials):
            loc = f"{kind}.{page_name}.dials[{dial_index}]"
            unknown = _unknown_entity(dial.entity_id, loc, known_entities)
            if unknown:
                issues.append(unknown)

    for field_name in ("state_entity_id", "brightness_entity_id"):
        unknown = _unknown_entity(getattr(config, field_name), field_name, known_entities)
        if unknown:
            issues.append(unknown)

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
