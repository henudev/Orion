from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.app import App
from app.models.deployment_config import DeploymentConfig
from app.models.environment import Environment
from app.schemas.deployment import DeployCreate, DeploymentRead
from app.schemas.deployment_config import DeploymentConfigCreate, DeploymentConfigRead, DeploymentConfigUpdate
from app.services.deploy_service import (
    create_deployment_record,
    process_deployment,
    resolve_image_ref,
    validate_deploy_request,
)

router = APIRouter(prefix="/deploy-configs", tags=["deploy-configs"])


def _decode_ports(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _decode_env_vars(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    return {}


def _to_read(model: DeploymentConfig) -> DeploymentConfigRead:
    return DeploymentConfigRead(
        id=model.id,
        name=model.name,
        description=model.description,
        app_id=model.app_id,
        environment_id=model.environment_id,
        mode=model.mode,
        build_id=model.build_id,
        image_ref=model.image_ref,
        container_name=model.container_name,
        ports=_decode_ports(model.ports_json),
        env_vars=_decode_env_vars(model.env_vars_json),
        compose_content=model.compose_content,
        remote_dir=model.remote_dir,
        timeout_seconds=model.timeout_seconds,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_deploy_payload(model: DeploymentConfig) -> DeployCreate:
    return DeployCreate(
        app_id=model.app_id,
        environment_id=model.environment_id,
        mode=model.mode,  # type: ignore[arg-type]
        build_id=model.build_id,
        image_ref=model.image_ref,
        container_name=model.container_name,
        ports=_decode_ports(model.ports_json),
        env_vars=_decode_env_vars(model.env_vars_json),
        compose_content=model.compose_content,
        remote_dir=model.remote_dir,
        timeout_seconds=model.timeout_seconds,
    )


def _assert_app_env_exists(db: Session, app_id: int, environment_id: int) -> None:
    if db.get(App, app_id) is None:
        raise HTTPException(status_code=404, detail=f"App {app_id} not found")
    if db.get(Environment, environment_id) is None:
        raise HTTPException(status_code=404, detail=f"Environment {environment_id} not found")


def _assert_unique_name(
    db: Session,
    app_id: int,
    environment_id: int,
    name: str,
    current_id: int | None = None,
) -> None:
    query = select(DeploymentConfig).where(
        DeploymentConfig.app_id == app_id,
        DeploymentConfig.environment_id == environment_id,
        DeploymentConfig.name == name,
    )
    existing = db.scalar(query)
    if existing is None:
        return
    if current_id is not None and existing.id == current_id:
        return
    raise HTTPException(status_code=409, detail="Deployment config name already exists for this app/environment")


@router.get("", response_model=list[DeploymentConfigRead])
def list_deploy_configs(
    app_id: int | None = None,
    environment_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> list[DeploymentConfigRead]:
    query = select(DeploymentConfig)
    if app_id is not None:
        query = query.where(DeploymentConfig.app_id == app_id)
    if environment_id is not None:
        query = query.where(DeploymentConfig.environment_id == environment_id)
    query = query.order_by(desc(DeploymentConfig.id)).limit(max(1, min(limit, 500)))
    return [_to_read(item) for item in db.scalars(query)]


@router.get("/{config_id}", response_model=DeploymentConfigRead)
def get_deploy_config(config_id: int, db: Session = Depends(get_db)) -> DeploymentConfigRead:
    config = db.get(DeploymentConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Deployment config not found")
    return _to_read(config)


@router.post("", response_model=DeploymentConfigRead, status_code=status.HTTP_201_CREATED)
def create_deploy_config(payload: DeploymentConfigCreate, db: Session = Depends(get_db)) -> DeploymentConfigRead:
    _assert_app_env_exists(db, payload.app_id, payload.environment_id)
    _assert_unique_name(db, payload.app_id, payload.environment_id, payload.name)

    config = DeploymentConfig(
        name=payload.name,
        description=payload.description,
        app_id=payload.app_id,
        environment_id=payload.environment_id,
        mode=payload.mode,
        build_id=payload.build_id,
        image_ref=payload.image_ref,
        container_name=payload.container_name,
        ports_json=json.dumps(payload.ports, ensure_ascii=False),
        env_vars_json=json.dumps(payload.env_vars, ensure_ascii=False),
        compose_content=payload.compose_content,
        remote_dir=payload.remote_dir,
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.put("/{config_id}", response_model=DeploymentConfigRead)
def update_deploy_config(
    config_id: int,
    payload: DeploymentConfigUpdate,
    db: Session = Depends(get_db),
) -> DeploymentConfigRead:
    config = db.get(DeploymentConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Deployment config not found")

    changes = payload.model_dump(exclude_unset=True)
    target_app_id = changes.get("app_id", config.app_id)
    target_environment_id = changes.get("environment_id", config.environment_id)
    target_name = changes.get("name", config.name)

    _assert_app_env_exists(db, target_app_id, target_environment_id)
    _assert_unique_name(db, target_app_id, target_environment_id, target_name, current_id=config.id)

    if "name" in changes:
        config.name = changes["name"]
    if "description" in changes:
        config.description = changes["description"]
    if "app_id" in changes:
        config.app_id = changes["app_id"]
    if "environment_id" in changes:
        config.environment_id = changes["environment_id"]
    if "mode" in changes:
        config.mode = changes["mode"]
    if "build_id" in changes:
        config.build_id = changes["build_id"]
    if "image_ref" in changes:
        config.image_ref = changes["image_ref"]
    if "container_name" in changes:
        config.container_name = changes["container_name"]
    if "ports" in changes:
        config.ports_json = json.dumps(changes["ports"], ensure_ascii=False)
    if "env_vars" in changes:
        config.env_vars_json = json.dumps(changes["env_vars"], ensure_ascii=False)
    if "compose_content" in changes:
        config.compose_content = changes["compose_content"]
    if "remote_dir" in changes:
        config.remote_dir = changes["remote_dir"]
    if "timeout_seconds" in changes:
        config.timeout_seconds = changes["timeout_seconds"]

    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.delete("/{config_id}")
def delete_deploy_config(config_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    config = db.get(DeploymentConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Deployment config not found")
    db.delete(config)
    db.commit()
    return {"detail": "deleted"}


@router.post("/{config_id}/run", response_model=DeploymentRead, status_code=status.HTTP_202_ACCEPTED)
async def run_deploy_config(config_id: int, db: Session = Depends(get_db)) -> DeploymentRead:
    config = db.get(DeploymentConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Deployment config not found")

    payload = _to_deploy_payload(config)
    try:
        validate_deploy_request(db, payload)
        image_ref, image_digest = resolve_image_ref(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deployment = create_deployment_record(db, payload, image_digest=image_digest)
    asyncio.create_task(process_deployment(deployment.id, payload, image_ref))
    return deployment
