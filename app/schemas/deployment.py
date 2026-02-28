from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeployCreate(BaseModel):
    app_id: int
    environment_id: int
    mode: Literal["run", "compose"]
    build_id: int | None = None
    image_ref: str | None = Field(default=None, description="镜像 tag 或 image@sha256:digest")
    container_name: str | None = "app-prod"
    ports: list[str] = Field(default_factory=list, description='格式 "8080:80"')
    env_vars: dict[str, str] = Field(default_factory=dict)
    compose_content: str | None = Field(default=None, description="compose 模式时可直接提交内容")
    remote_dir: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: int
    environment_id: int
    image_digest: str | None
    mode: str
    status: str
    log_file: str
    error_message: str | None
    created_at: datetime

