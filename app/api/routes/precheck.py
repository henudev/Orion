from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.schemas.precheck import PrecheckResponse
from app.services.precheck_service import local_precheck, remote_precheck

router = APIRouter(prefix="/precheck", tags=["precheck"])


@router.get("/local", response_model=PrecheckResponse)
async def local() -> PrecheckResponse:
    return await local_precheck(settings.orion_home)


@router.get("/remote/{env_id}", response_model=PrecheckResponse)
def remote(env_id: int, db: Session = Depends(get_db)) -> PrecheckResponse:
    return remote_precheck(db, env_id)

