"""Home Assistant REST client. The token stays on the server."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets

log = logging.getLogger("ha_streamdeck_gui.ha")

DOMAIN_SERVICE_HINTS: dict[str, str] = {
    "light": "light.toggle",
    "switch": "switch.toggle",
    "fan": "fan.toggle",
    "input_boolean": "input_boolean.toggle",
    "scene": "scene.turn_on",
    "script": "script.turn_on",
    "automation": "automation.trigger",
    "button": "button.press",
    "cover": "cover.toggle",
    "lock": "lock.toggle",
    "media_player": "media_player.media_play_pause",
    "climate": "climate.set_temperature",
    "vacuum": "vacuum.start",
    "input_number": "input_number.set_value",
    "input_select": "input_select.select_next",
    "timer": "timer.start",
    "siren": "siren.toggle",
}


class HomeAssistantError(RuntimeError):
    pass


@dataclass
class Entity:
    entity_id: str
    friendly_name: str
    domain: str
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        return f"{self.friendly_name} {self.entity_id} {self.domain} {self.state}".lower()


@dataclass
class EntityCache:
    entities: list[Entity] = field(default_factory=list)
    services: dict[str, list[str]] = field(default_factory=dict)
    fetched_at: str | None = None


_cache = EntityCache()


def normalize_ha_url(url: str) -> str:
    raw = url.strip().rstrip("/")
    if not raw:
        raise HomeAssistantError("Home Assistant URL is empty.")
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    if not parsed.hostname:
        raise HomeAssistantError("Home Assistant URL is missing a host.")
    if parsed.port is None and parsed.scheme in {"http", "https"}:
        # Match the upstream gotcha: port must be part of the URL, not assumed.
        pass
    return f"{parsed.scheme}://{parsed.netloc}"


def hass_streamdeck_endpoint(url: str) -> tuple[str, str]:
    """Host:port and ws/wss for home-assistant-streamdeck-yaml.

    Upstream often ignores a separate HASS_PORT and connects to 80. Always put
    the port on the host for http:// URLs.
    """
    base = normalize_ha_url(url)
    parsed = urlparse(base)
    if not parsed.hostname:
        raise HomeAssistantError("Home Assistant URL is missing a host.")
    protocol = "wss" if parsed.scheme == "https" else "ws"
    if parsed.port:
        host = f"{parsed.hostname}:{parsed.port}"
    elif parsed.scheme == "http":
        host = f"{parsed.hostname}:8123"
    else:
        host = parsed.hostname
    return host, protocol


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _client(url: str, token: str, timeout: float = 8.0) -> httpx.Client:
    return httpx.Client(base_url=url, headers=_headers(token), timeout=timeout)


def test_connection(url: str, token: str) -> dict[str, Any]:
    if not token:
        raise HomeAssistantError("Home Assistant token is not set.")
    base = normalize_ha_url(url)
    try:
        with _client(base, token) as client:
            response = client.get("/api/")
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        log.info("Home Assistant test failed with HTTP %s", exc.response.status_code)
        raise HomeAssistantError(
            f"Home Assistant returned HTTP {exc.response.status_code}. "
            "Check the URL (include the port, e.g. http://192.168.1.10:8123) and token.",
        ) from exc
    except httpx.RequestError as exc:
        log.info("Home Assistant test failed: connection error")
        raise HomeAssistantError(
            f"Could not reach {base}. Include the port in the URL if Home Assistant is not on 80/443.",
        ) from exc
    return {"ok": True, "message": body.get("message", "ok"), "url": base}


def test_websocket(url: str, token: str) -> dict[str, Any]:
    if not token:
        raise HomeAssistantError("Home Assistant token is not set.")
    host, protocol = hass_streamdeck_endpoint(url)
    uri = f"{protocol}://{host}/api/websocket"

    async def _run() -> dict[str, Any]:
        try:
            async with websockets.connect(uri, open_timeout=8, close_timeout=2, max_size=10_485_760) as socket:
                hello = json.loads(await asyncio.wait_for(socket.recv(), 8))
                if hello.get("type") != "auth_required":
                    raise HomeAssistantError(
                        f"Unexpected Home Assistant websocket hello: {hello.get('type')!r}",
                    )
                await socket.send(json.dumps({"type": "auth", "access_token": token.strip()}))
                reply = json.loads(await asyncio.wait_for(socket.recv(), 8))
        except TimeoutError as exc:
            raise HomeAssistantError(f"Timed out talking to {uri}") from exc
        except OSError as exc:
            raise HomeAssistantError(f"Could not open {uri}") from exc
        kind = reply.get("type")
        if kind == "auth_ok":
            return {"ok": True, "ha_version": reply.get("ha_version"), "uri": uri, "host": host, "protocol": protocol}
        if kind == "auth_invalid":
            raise HomeAssistantError(
                "Home Assistant rejected the token on the websocket. "
                "Create a new long-lived token in your profile and save it in Settings.",
            )
        raise HomeAssistantError(f"Unexpected Home Assistant auth reply: {kind!r}")

    return asyncio.run(_run())


def test_home_assistant(url: str, token: str) -> dict[str, Any]:
    rest = test_connection(url, token)
    websocket = test_websocket(url, token)
    return {"ok": True, "rest": rest, "websocket": websocket}


def refresh_cache(url: str, token: str) -> EntityCache:
    base = normalize_ha_url(url)
    if not token:
        raise HomeAssistantError("Home Assistant token is not set.")
    try:
        with _client(base, token, timeout=20.0) as client:
            states_resp = client.get("/api/states")
            states_resp.raise_for_status()
            services_resp = client.get("/api/services")
            services_resp.raise_for_status()
            states = states_resp.json()
            services_raw = services_resp.json()
    except httpx.HTTPError as exc:
        log.info("Home Assistant fetch failed")
        raise HomeAssistantError("Failed to fetch entities or services from Home Assistant.") from exc

    entities = []
    for item in states:
        entity_id = item.get("entity_id", "")
        domain = entity_id.split(".", 1)[0] if entity_id else ""
        attrs = item.get("attributes") or {}
        entities.append(
            Entity(
                entity_id=entity_id,
                friendly_name=str(attrs.get("friendly_name") or entity_id),
                domain=domain,
                state=str(item.get("state", "")),
                attributes=attrs,
            ),
        )
    entities.sort(key=lambda e: (e.domain, e.friendly_name.lower()))

    services: dict[str, list[str]] = {}
    for domain_entry in services_raw:
        domain = domain_entry.get("domain", "")
        names = sorted((domain_entry.get("services") or {}).keys())
        services[domain] = [f"{domain}.{name}" for name in names]

    _cache.entities = entities
    _cache.services = services
    _cache.fetched_at = datetime.now(timezone.utc).isoformat()
    return _cache


def get_cache() -> EntityCache:
    return _cache


def suggested_service(entity_id: str) -> str | None:
    domain = entity_id.split(".", 1)[0] if entity_id else ""
    if domain in DOMAIN_SERVICE_HINTS:
        return DOMAIN_SERVICE_HINTS[domain]
    cached = _cache.services.get(domain, [])
    for suffix in (".toggle", ".turn_on", ".press"):
        for service in cached:
            if service.endswith(suffix):
                return service
    return cached[0] if cached else None


def public_entities() -> list[dict[str, str]]:
    return [
        {
            "entity_id": entity.entity_id,
            "friendly_name": entity.friendly_name,
            "domain": entity.domain,
            "state": entity.state,
        }
        for entity in _cache.entities
    ]
