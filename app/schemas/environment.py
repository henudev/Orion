from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EnvironmentCreate(BaseModel):
    name: str
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str
    password: str

    @field_validator("name", "host", "username", "password")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


class EnvironmentUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None

    @field_validator("name", "host", "username", "password")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    host: str
    port: int
    username: str
    created_at: datetime


class EnvironmentConnectionTestRequest(BaseModel):
    host: str
    port: int = 22
    username: str
    password: str


class EnvironmentConnectionTestResponse(BaseModel):
    ok: bool
    detail: str
