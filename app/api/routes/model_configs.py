from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.model_config import ModelConfig
from app.schemas.model_config import (
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigTestResponse,
    ModelConfigUpdate,
)
from app.services.ai_model_service import test_model_connection

router = APIRouter(prefix="/model-configs", tags=["model-configs"])


def _to_read(model: ModelConfig) -> ModelConfigRead:
    return ModelConfigRead(
        id=model.id,
        name=model.name,
        provider=model.provider,
        base_url=model.base_url,
        model_name=model.model_name,
        api_key_set=bool(model.api_key),
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        is_default=model.is_default,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _ensure_name_unique(db: Session, name: str, current_id: int | None = None) -> None:
    existing = db.scalar(select(ModelConfig).where(ModelConfig.name == name))
    if existing is None:
        return
    if current_id is not None and existing.id == current_id:
        return
    raise HTTPException(status_code=409, detail="Model config name already exists")


def _unset_default_configs(db: Session, exclude_id: int | None = None) -> None:
    query = select(ModelConfig).where(ModelConfig.is_default.is_(True))
    if exclude_id is not None:
        query = query.where(ModelConfig.id != exclude_id)
    for item in db.scalars(query):
        item.is_default = False


@router.get("", response_model=list[ModelConfigRead])
def list_model_configs(limit: int = 200, db: Session = Depends(get_db)) -> list[ModelConfigRead]:
    query = select(ModelConfig).order_by(desc(ModelConfig.id)).limit(max(1, min(limit, 500)))
    return [_to_read(item) for item in db.scalars(query)]


@router.get("/{config_id}", response_model=ModelConfigRead)
def get_model_config(config_id: int, db: Session = Depends(get_db)) -> ModelConfigRead:
    config = db.get(ModelConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    return _to_read(config)


@router.post("", response_model=ModelConfigRead, status_code=status.HTTP_201_CREATED)
def create_model_config(payload: ModelConfigCreate, db: Session = Depends(get_db)) -> ModelConfigRead:
    _ensure_name_unique(db, payload.name)
    existing_count = db.scalar(select(ModelConfig.id).limit(1))
    is_default = payload.is_default or existing_count is None

    if is_default:
        _unset_default_configs(db)

    config = ModelConfig(
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        model_name=payload.model_name,
        api_key=payload.api_key,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_default=is_default,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.put("/{config_id}", response_model=ModelConfigRead)
def update_model_config(config_id: int, payload: ModelConfigUpdate, db: Session = Depends(get_db)) -> ModelConfigRead:
    config = db.get(ModelConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_name_unique(db, changes["name"], current_id=config.id)
        config.name = changes["name"]
    if "provider" in changes:
        config.provider = changes["provider"]
    if "base_url" in changes:
        config.base_url = changes["base_url"]
    if "model_name" in changes:
        config.model_name = changes["model_name"]
    if changes.get("clear_api_key"):
        config.api_key = None
    elif "api_key" in changes:
        config.api_key = changes["api_key"]
    if "temperature" in changes:
        config.temperature = changes["temperature"]
    if "max_tokens" in changes:
        config.max_tokens = changes["max_tokens"]
    if "is_default" in changes:
        config.is_default = bool(changes["is_default"])
        if config.is_default:
            _unset_default_configs(db, exclude_id=config.id)

    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.delete("/{config_id}")
def delete_model_config(config_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    config = db.get(ModelConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")

    was_default = config.is_default
    db.delete(config)
    db.commit()

    if was_default:
        latest = db.scalar(select(ModelConfig).order_by(desc(ModelConfig.id)).limit(1))
        if latest is not None:
            latest.is_default = True
            db.commit()

    return {"detail": "deleted"}


@router.post("/{config_id}/test-connection", response_model=ModelConfigTestResponse)
async def test_config_connection(config_id: int, db: Session = Depends(get_db)) -> ModelConfigTestResponse:
    config = db.get(ModelConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    ok, detail = await asyncio.to_thread(test_model_connection, config)
    return ModelConfigTestResponse(ok=ok, detail=detail)
