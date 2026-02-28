from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import apps, build_configs, builds, deploy, deploy_configs, environments, image_repo, precheck
from app.core.config import settings
from app.db.init_db import init_db
from app.services.build_service import start_build_workers, stop_build_workers
from app.services.path_manager import ensure_orion_layout


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_orion_layout()
    init_db()
    await start_build_workers()
    try:
        yield
    finally:
        await stop_build_workers()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(apps.router, prefix=settings.api_prefix)
app.include_router(environments.router, prefix=settings.api_prefix)
app.include_router(builds.router, prefix=settings.api_prefix)
app.include_router(build_configs.router, prefix=settings.api_prefix)
app.include_router(deploy.router, prefix=settings.api_prefix)
app.include_router(deploy_configs.router, prefix=settings.api_prefix)
app.include_router(image_repo.router, prefix=settings.api_prefix)
app.include_router(precheck.router, prefix=settings.api_prefix)

ui_dir = Path(__file__).parent / "ui"
assets_dir = ui_dir / "assets"
app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ui_dir / "index.html")
