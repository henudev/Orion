from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeploymentConfigCreate(BaseModel):
    name: str
    description: str | None = None
    app_id: int
    environment_id: int
    mode: Literal["run", "compose"]
    build_id: int | None = None
    image_ref: str | None = Field(default=None, description="镜像 tag 或 image@sha256:digest")
    container_name: str | None = "app-prod"
    ports: list[str] = Field(default_factory=list, description='格式 "8080:80"')
    env_vars: dict[str, str] = Field(default_factory=dict)
    compose_content: str | None = None
    remote_dir: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty")
        return normalized


class DeploymentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    app_id: int | None = None
    environment_id: int | None = None
    mode: Literal["run", "compose"] | None = None
    build_id: int | None = None
    image_ref: str | None = None
    container_name: str | None = None
    ports: list[str] | None = None
    env_vars: dict[str, str] | None = None
    compose_content: str | None = None
    remote_dir: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=60, le=7200)

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty")
        return normalized


class DeploymentConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    app_id: int
    environment_id: int
    mode: str
    build_id: int | None
    image_ref: str | None
    container_name: str | None
    ports: list[str]
    env_vars: dict[str, str]
    compose_content: str | None
    remote_dir: str | None
    timeout_seconds: int | None
    created_at: datetime
    updated_at: datetime
