from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.deployment import DeploymentRead
from app.schemas.precheck import PrecheckResponse


class ImageRepositoryItem(BaseModel):
    repository: str
    tag: str
    image_ref: str
    image_id: str
    image_id_full: str
    digest: str | None = None
    created_at: datetime | None = None
    size_bytes: int | None = None


class ImageRepositoryListResponse(BaseModel):
    items: list[ImageRepositoryItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class ImageDeleteRequest(BaseModel):
    image_ref: str = Field(description="要删除的本地镜像引用")
    force: bool = Field(default=False, description="是否强制删除")


class ImageDeleteResponse(BaseModel):
    ok: bool
    image_ref: str
    detail: str


class ImageDeployCreate(BaseModel):
    app_id: int
    environment_id: int
    image_ref: str = Field(description="镜像引用，支持 repo:tag / repo@sha256 / image id")
    mode: Literal["run", "compose"] = "run"
    container_name: str | None = "app-prod"
    ports: list[str] = Field(default_factory=list, description='格式 "8080:80"')
    env_vars: dict[str, str] = Field(default_factory=dict)
    compose_content: str | None = None
    remote_dir: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)


class ImageDeployResult(BaseModel):
    deployment: DeploymentRead
    precheck: PrecheckResponse
