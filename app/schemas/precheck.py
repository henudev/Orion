from __future__ import annotations

from pydantic import BaseModel


class PrecheckItem(BaseModel):
    name: str
    ok: bool
    detail: str


class PrecheckResponse(BaseModel):
    ok: bool
    items: list[PrecheckItem]

