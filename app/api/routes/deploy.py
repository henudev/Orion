from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.deployment import Deployment
from app.schemas.deployment import DeployCreate, DeploymentRead
from app.services.log_reader import read_lines_by_marker
from app.services.deploy_service import (
    create_deployment_record,
    process_deployment,
    resolve_image_ref,
    validate_deploy_request,
)

router = APIRouter(prefix="/deploy", tags=["deploy"])


@router.get("", response_model=list[DeploymentRead])
def list_deployments(
    app_id: int | None = None,
    environment_id: int | None = None,
    mode: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Deployment]:
    query = select(Deployment)
    if app_id is not None:
        query = query.where(Deployment.app_id == app_id)
    if environment_id is not None:
        query = query.where(Deployment.environment_id == environment_id)
    if mode is not None:
        query = query.where(Deployment.mode == mode)
    query = query.order_by(desc(Deployment.id)).limit(max(1, min(limit, 500)))
    return list(db.scalars(query))


@router.post("", response_model=DeploymentRead, status_code=status.HTTP_202_ACCEPTED)
async def create_deploy(payload: DeployCreate, db: Session = Depends(get_db)) -> Deployment:
    try:
        validate_deploy_request(db, payload)
        image_ref, image_digest = resolve_image_ref(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deployment = create_deployment_record(db, payload, image_digest=image_digest)
    asyncio.create_task(process_deployment(deployment.id, payload, image_ref))
    return deployment


@router.get("/{deploy_id}", response_model=DeploymentRead)
def get_deploy(deploy_id: int, db: Session = Depends(get_db)) -> Deployment:
    deployment = db.get(Deployment, deploy_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.get("/{deploy_id}/logs")
def get_deploy_logs(deploy_id: int, tail: int = 200, db: Session = Depends(get_db)) -> dict:
    deployment = db.get(Deployment, deploy_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")

    lines = read_lines_by_marker(deployment.log_file, f"[DEPLOY_ID={deploy_id}]", tail=tail)
    return {"deploy_id": deploy_id, "lines": lines}
