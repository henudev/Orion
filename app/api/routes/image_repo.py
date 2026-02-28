from __future__ import annotations

import asyncio
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.deployment import DeployCreate
from app.schemas.image_repo import (
    ImageDeployCreate,
    ImageDeployResult,
    ImageRepositoryItem,
    ImageRepositoryListResponse,
)
from app.services.deploy_service import (
    create_deployment_record,
    process_deployment,
    resolve_image_ref,
    validate_deploy_request,
)
from app.services.image_repo_service import ensure_local_image_exists, list_local_images
from app.services.precheck_service import remote_precheck

router = APIRouter(prefix="/image-repo", tags=["image-repo"])


@router.get("/images", response_model=ImageRepositoryListResponse)
async def list_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ImageRepositoryListResponse:
    try:
        all_items = [ImageRepositoryItem.model_validate(item) for item in await list_local_images(limit=None)]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    total = len(all_items)
    total_pages = ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    end = start + page_size
    return ImageRepositoryListResponse(
        items=all_items[start:end],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/deploy", response_model=ImageDeployResult, status_code=status.HTTP_202_ACCEPTED)
async def deploy_image(payload: ImageDeployCreate, db: Session = Depends(get_db)) -> ImageDeployResult:
    deploy_payload = DeployCreate(
        app_id=payload.app_id,
        environment_id=payload.environment_id,
        mode=payload.mode,
        image_ref=payload.image_ref,
        container_name=payload.container_name,
        ports=payload.ports,
        env_vars=payload.env_vars,
        compose_content=payload.compose_content,
        remote_dir=payload.remote_dir,
        timeout_seconds=payload.timeout_seconds,
    )

    precheck = remote_precheck(db, payload.environment_id)
    if not precheck.ok:
        failed_items = [f"{item.name}: {item.detail}" for item in precheck.items if not item.ok]
        detail = "remote precheck failed"
        if failed_items:
            detail = f"{detail}: {'; '.join(failed_items)}"
        raise HTTPException(status_code=400, detail=detail)

    try:
        await ensure_local_image_exists(payload.image_ref)
        validate_deploy_request(db, deploy_payload)
        image_ref, image_digest = resolve_image_ref(db, deploy_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deployment = create_deployment_record(db, deploy_payload, image_digest=image_digest)
    asyncio.create_task(process_deployment(deployment.id, deploy_payload, image_ref))
    return ImageDeployResult(deployment=deployment, precheck=precheck)
