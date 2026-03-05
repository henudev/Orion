from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.constants import BUILD_STATUS_SUCCESS
from app.core.timezone import to_orion
from app.models.build import Build
from app.schemas.deployment import DeployCreate
from app.schemas.image_repo import (
    ImageDeleteRequest,
    ImageDeleteResponse,
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
from app.services.image_repo_service import delete_local_image, ensure_local_image_exists, list_local_images
from app.services.precheck_service import remote_precheck

router = APIRouter(prefix="/image-repo", tags=["image-repo"])


def _normalize_build_tag(image_tag: str | None) -> str | None:
    if image_tag is None:
        return None
    value = image_tag.strip()
    if not value:
        return None
    if "@sha256:" in value:
        return value
    tail = value.rsplit("/", 1)[-1]
    if ":" in tail:
        return value
    return f"{value}:latest"


def _item_tag_ref(item: ImageRepositoryItem) -> str | None:
    if item.repository != "<none>" and item.tag != "<none>":
        return f"{item.repository}:{item.tag}"
    if item.image_ref and "@sha256:" in item.image_ref:
        return item.image_ref
    return None


def _sort_key(dt: datetime | None) -> datetime:
    normalized = to_orion(dt)
    if normalized is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc)


def _overlay_orion_build_time(db: Session, items: list[ImageRepositoryItem]) -> list[ImageRepositoryItem]:
    if not items:
        return items

    refs = {ref for ref in (_item_tag_ref(item) for item in items) if ref}
    if not refs:
        items.sort(key=lambda item: _sort_key(item.created_at), reverse=True)
        return items

    rows = db.execute(
        select(Build.image_tag, Build.created_at)
        .where(Build.status == BUILD_STATUS_SUCCESS)
        .order_by(desc(Build.id))
    ).all()

    latest_build_time: dict[str, datetime] = {}
    for image_tag, created_at in rows:
        normalized = _normalize_build_tag(image_tag)
        if normalized is None or normalized not in refs or normalized in latest_build_time:
            continue
        if created_at is not None:
            latest_build_time[normalized] = created_at
        if len(latest_build_time) >= len(refs):
            break

    for item in items:
        ref = _item_tag_ref(item)
        if ref and ref in latest_build_time:
            item.created_at = latest_build_time[ref]

    items.sort(key=lambda item: _sort_key(item.created_at), reverse=True)
    return items


@router.get("/images", response_model=ImageRepositoryListResponse)
async def list_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ImageRepositoryListResponse:
    try:
        all_items = [ImageRepositoryItem.model_validate(item) for item in await list_local_images(limit=None)]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    all_items = _overlay_orion_build_time(db, all_items)

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


@router.post("/images/delete", response_model=ImageDeleteResponse)
async def delete_image(payload: ImageDeleteRequest) -> ImageDeleteResponse:
    try:
        detail = await delete_local_image(payload.image_ref, force=payload.force)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImageDeleteResponse(ok=True, image_ref=payload.image_ref, detail=detail)
