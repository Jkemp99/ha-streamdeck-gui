"""FastAPI application."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from ha_streamdeck_gui import __version__
from ha_streamdeck_gui.assets import (
    AssetsError,
    asset_path,
    list_assets,
    resolve_assets_dir,
    save_asset,
)
from ha_streamdeck_gui.decks import get_deck_model, list_deck_models
from ha_streamdeck_gui.deck_service import (
    SERVICE_NAME,
    DeckServiceError,
    apply_from_settings,
    service_status as deck_service_status,
    start_user_service,
)
from ha_streamdeck_gui.ha import (
    HomeAssistantError,
    get_cache,
    public_entities,
    refresh_cache,
    suggested_service,
    test_home_assistant,
)
from ha_streamdeck_gui.lint import Issue, lint_config
from ha_streamdeck_gui.sample import build_sample_config, sample_yaml
from ha_streamdeck_gui.schema import SPECIAL_TYPES, StreamDeckConfig
from ha_streamdeck_gui.settings import (
    load_settings,
    merge_settings,
    public_settings,
    save_settings,
)
from ha_streamdeck_gui.yaml_io import (
    IncludeProtectedError,
    backup_dir_for,
    dump_config_yaml,
    list_backups,
    load_yaml_file,
    parse_yaml_text,
    restore_backup,
    save_yaml_file,
    yaml_diff,
)

log = logging.getLogger("ha_streamdeck_gui")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="HA Stream Deck GUI",
    version=__version__,
    description="Visual editor for home-assistant-streamdeck-yaml. No auth by default (LAN only).",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SettingsUpdate(BaseModel):
    streamdeck_yaml_path: str | None = None
    ha_url: str | None = None
    ha_token: str | None = None
    deck_model: str | None = None
    backup_count: int | None = None
    systemd_service_name: str | None = None
    assets_dir: str | None = None


class ConfigPayload(BaseModel):
    config: dict[str, Any] | None = None
    yaml_text: str | None = None
    path: str | None = None
    allow_inline_includes: bool = False


def _configured_path(explicit: str | None = None) -> Path:
    settings = load_settings()
    raw = explicit or settings.streamdeck_yaml_path
    if not raw:
        raise HTTPException(400, "No streamdeck.yaml path configured.")
    return Path(raw).expanduser()


def _cache_is_fresh(seconds: int = 30) -> bool:
    fetched = get_cache().fetched_at
    if not fetched:
        return False
    try:
        stamp = datetime.fromisoformat(fetched)
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - stamp < timedelta(seconds=seconds)


def _known_entities(*, refresh: bool) -> set[str] | None:
    settings = load_settings()
    if refresh and settings.ha_url and settings.ha_token.strip() and not _cache_is_fresh():
        try:
            refresh_cache(settings.ha_url, settings.ha_token)
        except HomeAssistantError:
            pass
    if not get_cache().fetched_at:
        return None
    return {entity.entity_id for entity in get_cache().entities}


def _issue_payload(issue: Issue) -> dict[str, str]:
    payload = {
        "severity": issue.severity,
        "code": issue.code,
        "message": issue.message,
        "path": issue.path,
    }
    if issue.entity_id:
        payload["entity_id"] = issue.entity_id
    return payload


def _issues_for(
    config: StreamDeckConfig,
    *,
    has_includes: bool = False,
    refresh: bool = False,
) -> list[dict[str, str]]:
    settings = load_settings()
    deck = get_deck_model(settings.deck_model)
    return [
        _issue_payload(issue)
        for issue in lint_config(
            config,
            deck=deck,
            known_entities=_known_entities(refresh=refresh),
            has_includes=has_includes,
        )
    ]


def _reject_lint_errors(issues: list[dict[str, str]]) -> None:
    hard = [issue for issue in issues if issue["severity"] == "error"]
    if not hard:
        return
    unknown = [issue.get("entity_id") or "" for issue in hard if issue["code"] == "unknown_entity"]
    names = ", ".join(sorted({name for name in unknown if name}))
    message = (
        f"These entity_ids are not in Home Assistant and will crash the Stream Deck: {names}"
        if names
        else "Validation failed"
    )
    raise HTTPException(400, {"message": message, "issues": issues})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


@app.get("/api/deck-models")
def deck_models() -> list[dict[str, Any]]:
    return [model.model_dump() for model in list_deck_models()]


@app.get("/api/schema")
def schema_meta() -> dict[str, Any]:
    return {
        "special_types": list(SPECIAL_TYPES),
        "light_control_keys": ["colors", "colormap", "color_temp_kelvin", "brightnesses"],
        "long_press_keys": [
            "service",
            "service_data",
            "entity_id",
            "target",
            "special_type",
            "special_type_data",
        ],
        "dial_event_types": ["TURN", "PUSH"],
    }


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return public_settings(load_settings()).model_dump()


@app.put("/api/settings")
def put_settings(update: SettingsUpdate) -> dict[str, Any]:
    current = load_settings()
    merged = merge_settings(current, update.model_dump(exclude_none=True))
    save_settings(merged)
    return public_settings(merged).model_dump()


@app.get("/api/config")
def get_config(path: str | None = None) -> dict[str, Any]:
    target = _configured_path(path)
    if not target.is_file():
        raise HTTPException(404, f"File not found: {target}")
    loaded = load_yaml_file(target)
    return {
        "path": str(target),
        "yaml_text": loaded.text,
        "config": loaded.config.model_dump(),
        "has_includes": loaded.has_includes,
        "include_paths": loaded.include_paths,
        "issues": _issues_for(loaded.config, has_includes=loaded.has_includes, refresh=True),
    }


@app.post("/api/config/validate")
def validate_config(payload: ConfigPayload) -> dict[str, Any]:
    try:
        if payload.yaml_text is not None:
            loaded = parse_yaml_text(payload.yaml_text)
            config = loaded.config
            has_includes = loaded.has_includes
        elif payload.config is not None:
            config = StreamDeckConfig.model_validate(payload.config)
            has_includes = False
        else:
            raise HTTPException(400, "Provide config or yaml_text.")
    except ValidationError as exc:
        return {"ok": False, "errors": exc.errors(), "issues": []}
    issues = _issues_for(config, has_includes=has_includes, refresh=True)
    hard = [issue for issue in issues if issue["severity"] == "error"]
    return {
        "ok": not hard,
        "config": config.model_dump(),
        "issues": issues,
        "errors": [],
    }


@app.post("/api/config/diff")
def diff_config(payload: ConfigPayload) -> dict[str, Any]:
    target = _configured_path(payload.path)
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    if payload.yaml_text is not None:
        proposed = payload.yaml_text
        config = parse_yaml_text(proposed).config
    elif payload.config is not None:
        config = StreamDeckConfig.model_validate(payload.config)
        proposed = dump_config_yaml(config)
    else:
        raise HTTPException(400, "Provide config or yaml_text.")
    return {
        "diff": yaml_diff(current, proposed),
        "proposed": proposed,
        "issues": _issues_for(config),
    }


@app.put("/api/config")
def put_config(payload: ConfigPayload) -> dict[str, Any]:
    settings = load_settings()
    target = _configured_path(payload.path)
    try:
        if payload.yaml_text is not None:
            loaded = parse_yaml_text(payload.yaml_text, path=target)
            issues = _issues_for(loaded.config, has_includes=loaded.has_includes, refresh=True)
            _reject_lint_errors(issues)
            backup = save_yaml_file(
                target,
                text=payload.yaml_text,
                backup_count=settings.backup_count,
                allow_inline_includes=payload.allow_inline_includes,
            )
            config = loaded.config
        elif payload.config is not None:
            config = StreamDeckConfig.model_validate(payload.config)
            issues = _issues_for(config, refresh=True)
            _reject_lint_errors(issues)
            original = load_yaml_file(target) if target.is_file() else None
            backup = save_yaml_file(
                target,
                config=config,
                backup_count=settings.backup_count,
                allow_inline_includes=payload.allow_inline_includes,
                original=original,
            )
        else:
            raise HTTPException(400, "Provide config or yaml_text.")
    except IncludeProtectedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(400, {"message": "Invalid config", "errors": exc.errors()}) from exc
    return {
        "ok": True,
        "path": str(target),
        "backup": str(backup) if backup else None,
        "issues": issues,
        "config": config.model_dump(),
    }


@app.get("/api/backups")
def get_backups(path: str | None = None) -> list[dict[str, str]]:
    return list_backups(_configured_path(path))


@app.post("/api/backups/restore")
def post_restore(name: str, path: str | None = None) -> dict[str, Any]:
    settings = load_settings()
    target = _configured_path(path)
    backup = backup_dir_for(target) / name
    if not backup.is_file():
        raise HTTPException(404, f"Backup not found: {name}")
    restore_backup(backup, target, backup_count=settings.backup_count)
    loaded = load_yaml_file(target)
    return {"ok": True, "config": loaded.config.model_dump(), "yaml_text": loaded.text}


@app.get("/api/sample")
def get_sample() -> dict[str, Any]:
    config = build_sample_config()
    return {"yaml_text": sample_yaml(), "config": config.model_dump()}


@app.post("/api/sample/write")
def write_sample(path: str | None = None) -> dict[str, Any]:
    settings = load_settings()
    target = _configured_path(path)
    backup = save_yaml_file(
        target,
        text=sample_yaml(),
        backup_count=settings.backup_count,
        allow_inline_includes=True,
    )
    return {"ok": True, "path": str(target), "backup": str(backup) if backup else None}


def _assets_root() -> Path:
    try:
        return resolve_assets_dir(load_settings())
    except AssetsError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/assets")
def get_assets() -> dict[str, Any]:
    root = _assets_root()
    return {"dir": str(root), "items": list_assets(root)}


@app.post("/api/assets")
async def post_asset(file: UploadFile = File(...)) -> dict[str, str]:
    root = _assets_root()
    data = await file.read()
    try:
        return save_asset(root, file.filename or "icon.png", data)
    except AssetsError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/assets/{name}")
def get_asset(name: str) -> FileResponse:
    root = _assets_root()
    try:
        path = asset_path(root, name)
    except AssetsError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not path.is_file():
        raise HTTPException(404, f"Asset not found: {name}")
    return FileResponse(path)


@app.post("/api/ha/test")
def ha_test() -> dict[str, Any]:
    settings = load_settings()
    try:
        return test_home_assistant(settings.ha_url, settings.ha_token)
    except HomeAssistantError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/ha/refresh")
def ha_refresh() -> dict[str, Any]:
    settings = load_settings()
    try:
        cache = refresh_cache(settings.ha_url, settings.ha_token)
    except HomeAssistantError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "ok": True,
        "fetched_at": cache.fetched_at,
        "entity_count": len(cache.entities),
        "domain_count": len(cache.services),
    }


@app.get("/api/ha/entities")
def ha_entities() -> dict[str, Any]:
    cache = get_cache()
    return {"fetched_at": cache.fetched_at, "entities": public_entities()}


@app.get("/api/ha/services")
def ha_services() -> dict[str, Any]:
    cache = get_cache()
    return {"fetched_at": cache.fetched_at, "services": cache.services}


@app.get("/api/ha/suggest-service")
def ha_suggest(entity_id: str) -> dict[str, str | None]:
    return {"service": suggested_service(entity_id)}


@app.get("/api/service/status")
def service_status() -> dict[str, Any]:
    return deck_service_status()


@app.post("/api/service/apply")
def service_apply() -> dict[str, Any]:
    settings = load_settings()
    try:
        test_home_assistant(settings.ha_url, settings.ha_token)
        result = apply_from_settings(settings)
    except (HomeAssistantError, DeckServiceError) as exc:
        raise HTTPException(400, str(exc)) from exc
    merged = merge_settings(settings, {"systemd_service_name": SERVICE_NAME})
    save_settings(merged)
    return result


@app.post("/api/service/restart")
def service_restart() -> dict[str, Any]:
    try:
        start_user_service()
    except DeckServiceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **deck_service_status()}


def create_app() -> FastAPI:
    return app


def run() -> None:
    settings = load_settings()
    host = os.environ.get("HOST", settings.host)
    port = int(os.environ.get("PORT", settings.port))
    logging.basicConfig(level=logging.INFO)
    log.info("Starting HA Stream Deck GUI on %s:%s (no authentication)", host, port)
    uvicorn.run("ha_streamdeck_gui.app:app", host=host, port=port, reload=False)
