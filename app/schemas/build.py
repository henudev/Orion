from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BuildCreate(BaseModel):
    app_id: int
    image_tag: str = Field(description="目标镜像 tag，例如 orion/demo:latest")
    dockerfile_content: str | None = Field(default=None, description="在线编辑 Dockerfile 内容")
    context_path: str | None = Field(default=None, description="构建上下文目录，默认 ~/Orion/workspace/{app_name}")
    build_args: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)


class BuildRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: int
    image_tag: str
    image_digest: str | None
    status: str
    log_file: str
    error_message: str | None
    created_at: datetime


class BuildLogsRead(BaseModel):
    build_id: int
    lines: list[str]

