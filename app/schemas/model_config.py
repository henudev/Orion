from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderType = Literal["openai", "ollama"]


class ModelConfigCreate(BaseModel):
    name: str
    provider: ProviderType
    base_url: str
    model_name: str
    api_key: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    is_default: bool = False

    @field_validator("name", "base_url", "model_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None


class ModelConfigUpdate(BaseModel):
    name: str | None = None
    provider: ProviderType | None = None
    base_url: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    is_default: bool | None = None

    @field_validator("name", "base_url", "model_name")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: ProviderType
    base_url: str
    model_name: str
    api_key_set: bool
    temperature: float | None
    max_tokens: int | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ModelConfigTestResponse(BaseModel):
    ok: bool
    detail: str


class DockerfileGenerateRequest(BaseModel):
    model_config_id: int
    requirement: str

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("requirement cannot be empty")
        return normalized


class DockerfileGenerateResponse(BaseModel):
    model_config_id: int
    provider: ProviderType
    model_name: str
    dockerfile_content: str
