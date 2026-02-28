from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.deployment import Deployment
from app.models.deployment_config import DeploymentConfig
from app.models.environment import Environment
from app.schemas.environment import (
    EnvironmentConnectionTestRequest,
    EnvironmentConnectionTestResponse,
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
)
from app.services.ssh_service import test_ssh_connection

router = APIRouter(prefix="/environments", tags=["environments"])


@router.post("", response_model=EnvironmentRead, status_code=status.HTTP_201_CREATED)
def create_environment(payload: EnvironmentCreate, db: Session = Depends(get_db)) -> Environment:
    exists = db.scalar(select(Environment).where(Environment.name == payload.name, Environment.host == payload.host))
    if exists is not None:
        raise HTTPException(status_code=409, detail="Environment already exists")

    env = Environment(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        ssh_key_path="",
    )
    db.add(env)
    db.commit()
    db.refresh(env)
    return env


@router.get("", response_model=list[EnvironmentRead])
def list_environments(db: Session = Depends(get_db)) -> list[Environment]:
    return list(db.scalars(select(Environment).order_by(Environment.id.desc())))


@router.put("/{env_id}", response_model=EnvironmentRead)
def update_environment(env_id: int, payload: EnvironmentUpdate, db: Session = Depends(get_db)) -> Environment:
    env = db.get(Environment, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    changes = payload.model_dump(exclude_unset=True)
    target_name = changes.get("name", env.name)
    target_host = changes.get("host", env.host)
    duplicate = db.scalar(
        select(Environment).where(Environment.name == target_name, Environment.host == target_host, Environment.id != env_id)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Environment already exists")

    if "name" in changes:
        env.name = changes["name"]
    if "host" in changes:
        env.host = changes["host"]
    if "port" in changes:
        env.port = changes["port"]
    if "username" in changes:
        env.username = changes["username"]
    if "password" in changes:
        env.password = changes["password"]

    db.commit()
    db.refresh(env)
    return env


@router.delete("/{env_id}")
def delete_environment(env_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    env = db.get(Environment, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    has_deployments = db.scalar(select(Deployment.id).where(Deployment.environment_id == env_id).limit(1)) is not None
    has_deploy_configs = (
        db.scalar(select(DeploymentConfig.id).where(DeploymentConfig.environment_id == env_id).limit(1)) is not None
    )
    if has_deployments or has_deploy_configs:
        raise HTTPException(status_code=409, detail="Cannot delete environment with existing deployments/configs")

    db.delete(env)
    db.commit()
    return {"detail": "deleted"}


@router.post("/test-connection", response_model=EnvironmentConnectionTestResponse)
def test_connection(payload: EnvironmentConnectionTestRequest) -> EnvironmentConnectionTestResponse:
    return test_ssh_connection(
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
    )


@router.post("/{env_id}/test-connection", response_model=EnvironmentConnectionTestResponse)
def test_saved_env_connection(env_id: int, db: Session = Depends(get_db)) -> EnvironmentConnectionTestResponse:
    env = db.get(Environment, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return test_ssh_connection(
        host=env.host,
        port=env.port,
        username=env.username,
        password=env.password,
    )
