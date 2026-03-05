from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.model_config import ModelConfig
from app.schemas.model_config import DockerfileGenerateRequest, DockerfileGenerateResponse
from app.services.ai_model_service import AIModelError, generate_dockerfile

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate-dockerfile", response_model=DockerfileGenerateResponse)
async def generate_dockerfile_by_ai(
    payload: DockerfileGenerateRequest,
    db: Session = Depends(get_db),
) -> DockerfileGenerateResponse:
    config = db.get(ModelConfig, payload.model_config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")

    try:
        dockerfile_content = await asyncio.to_thread(generate_dockerfile, config, payload.requirement)
    except AIModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DockerfileGenerateResponse(
        model_config_id=config.id,
        provider=config.provider,
        model_name=config.model_name,
        dockerfile_content=dockerfile_content,
    )
