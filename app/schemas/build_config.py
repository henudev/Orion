from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BuildConfigCreate(BaseModel):
    name: str
    description: str | None = None
    app_id: int
    image_tag: str = Field(description="目标镜像 tag，例如 orion/demo:latest")
    dockerfile_content: str | None = Field(default=None, description="在线编辑 Dockerfile 内容")
    context_path: str | None = Field(default=None, description="构建上下文目录，默认 ~/Orion/workspace/{app_name}")
    build_args: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty")
        return normalized


class BuildConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    app_id: int | None = None
    image_tag: str | None = None
    dockerfile_content: str | None = None
    context_path: str | None = None
    build_args: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty")
        return normalized


class BuildConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    app_id: int
    image_tag: str
    dockerfile_content: str | None
    context_path: str | None
    build_args: dict[str, str]
    timeout_seconds: int | None
    created_at: datetime
    updated_at: datetime

