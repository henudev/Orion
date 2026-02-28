from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.app import App
from app.models.build import Build
from app.models.build_config import BuildConfig
from app.models.deployment import Deployment
from app.models.deployment_config import DeploymentConfig
from app.schemas.app import AppCreate, AppRead, AppUpdate

router = APIRouter(prefix="/apps", tags=["apps"])


@router.post("", response_model=AppRead, status_code=status.HTTP_201_CREATED)
def create_app(payload: AppCreate, db: Session = Depends(get_db)) -> App:
    exists = db.scalar(select(App).where(App.name == payload.name))
    if exists is not None:
        raise HTTPException(status_code=409, detail="App name already exists")

    app = App(name=payload.name, description=payload.description)
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.get("", response_model=list[AppRead])
def list_apps(db: Session = Depends(get_db)) -> list[App]:
    return list(db.scalars(select(App).order_by(App.id.desc())))


@router.put("/{app_id}", response_model=AppRead)
def update_app(app_id: int, payload: AppUpdate, db: Session = Depends(get_db)) -> App:
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")

    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes:
        new_name = changes["name"]
        if new_name is None:
            raise HTTPException(status_code=422, detail="name cannot be null")
        if new_name != app.name:
            exists = db.scalar(select(App).where(App.name == new_name))
            if exists is not None:
                raise HTTPException(status_code=409, detail="App name already exists")
            app.name = new_name

    if "description" in changes:
        app.description = changes["description"]

    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}")
def delete_app(app_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")

    has_build = db.scalar(select(Build.id).where(Build.app_id == app_id).limit(1)) is not None
    has_build_config = db.scalar(select(BuildConfig.id).where(BuildConfig.app_id == app_id).limit(1)) is not None
    has_deploy_config = (
        db.scalar(select(DeploymentConfig.id).where(DeploymentConfig.app_id == app_id).limit(1)) is not None
    )
    has_deploy = db.scalar(select(Deployment.id).where(Deployment.app_id == app_id).limit(1)) is not None
    if has_build or has_build_config or has_deploy_config or has_deploy:
        raise HTTPException(status_code=409, detail="Cannot delete app with existing builds/configs/deployments")

    db.delete(app)
    db.commit()
    return {"detail": "deleted"}
