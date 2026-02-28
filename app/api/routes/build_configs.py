from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.app import App
from app.models.build_config import BuildConfig
from app.schemas.build import BuildCreate, BuildRead
from app.schemas.build_config import BuildConfigCreate, BuildConfigRead, BuildConfigUpdate
from app.services.build_service import create_build_if_app_exists, enqueue_build

router = APIRouter(prefix="/build-configs", tags=["build-configs"])


def _decode_build_args(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    return {}


def _to_read(model: BuildConfig) -> BuildConfigRead:
    return BuildConfigRead(
        id=model.id,
        name=model.name,
        description=model.description,
        app_id=model.app_id,
        image_tag=model.image_tag,
        dockerfile_content=model.dockerfile_content,
        context_path=model.context_path,
        build_args=_decode_build_args(model.build_args_json),
        timeout_seconds=model.timeout_seconds,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_build_payload(model: BuildConfig) -> BuildCreate:
    return BuildCreate(
        app_id=model.app_id,
        image_tag=model.image_tag,
        dockerfile_content=model.dockerfile_content,
        context_path=model.context_path,
        build_args=_decode_build_args(model.build_args_json),
        timeout_seconds=model.timeout_seconds,
    )


def _assert_app_exists(db: Session, app_id: int) -> None:
    if db.get(App, app_id) is None:
        raise HTTPException(status_code=404, detail=f"App {app_id} not found")


def _assert_unique_name(db: Session, app_id: int, name: str, current_id: int | None = None) -> None:
    query = select(BuildConfig).where(BuildConfig.app_id == app_id, BuildConfig.name == name)
    existing = db.scalar(query)
    if existing is None:
        return
    if current_id is not None and existing.id == current_id:
        return
    raise HTTPException(status_code=409, detail="Build config name already exists for this app")


@router.get("", response_model=list[BuildConfigRead])
def list_build_configs(
    app_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> list[BuildConfigRead]:
    query = select(BuildConfig)
    if app_id is not None:
        query = query.where(BuildConfig.app_id == app_id)
    query = query.order_by(desc(BuildConfig.id)).limit(max(1, min(limit, 500)))
    return [_to_read(item) for item in db.scalars(query)]


@router.get("/{config_id}", response_model=BuildConfigRead)
def get_build_config(config_id: int, db: Session = Depends(get_db)) -> BuildConfigRead:
    config = db.get(BuildConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Build config not found")
    return _to_read(config)


@router.post("", response_model=BuildConfigRead, status_code=status.HTTP_201_CREATED)
def create_build_config(payload: BuildConfigCreate, db: Session = Depends(get_db)) -> BuildConfigRead:
    _assert_app_exists(db, payload.app_id)
    _assert_unique_name(db, payload.app_id, payload.name)

    config = BuildConfig(
        name=payload.name,
        description=payload.description,
        app_id=payload.app_id,
        image_tag=payload.image_tag,
        dockerfile_content=payload.dockerfile_content,
        context_path=payload.context_path,
        build_args_json=json.dumps(payload.build_args, ensure_ascii=False),
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.put("/{config_id}", response_model=BuildConfigRead)
def update_build_config(config_id: int, payload: BuildConfigUpdate, db: Session = Depends(get_db)) -> BuildConfigRead:
    config = db.get(BuildConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Build config not found")

    changes = payload.model_dump(exclude_unset=True)
    target_app_id = changes.get("app_id", config.app_id)
    target_name = changes.get("name", config.name)

    _assert_app_exists(db, target_app_id)
    _assert_unique_name(db, target_app_id, target_name, current_id=config.id)

    if "name" in changes:
        config.name = changes["name"]
    if "description" in changes:
        config.description = changes["description"]
    if "app_id" in changes:
        config.app_id = changes["app_id"]
    if "image_tag" in changes:
        config.image_tag = changes["image_tag"]
    if "dockerfile_content" in changes:
        config.dockerfile_content = changes["dockerfile_content"]
    if "context_path" in changes:
        config.context_path = changes["context_path"]
    if "build_args" in changes:
        config.build_args_json = json.dumps(changes["build_args"], ensure_ascii=False)
    if "timeout_seconds" in changes:
        config.timeout_seconds = changes["timeout_seconds"]

    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.delete("/{config_id}")
def delete_build_config(config_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    config = db.get(BuildConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Build config not found")
    db.delete(config)
    db.commit()
    return {"detail": "deleted"}


@router.post("/{config_id}/run", response_model=BuildRead, status_code=status.HTTP_202_ACCEPTED)
async def run_build_config(config_id: int, db: Session = Depends(get_db)) -> BuildRead:
    config = db.get(BuildConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Build config not found")

    payload = _to_build_payload(config)
    try:
        build = create_build_if_app_exists(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await enqueue_build(build.id, payload)
    return build

