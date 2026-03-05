from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_orion_naive
from app.db.base import Base


class BuildConfig(Base):
    __tablename__ = "build_configs"
    __table_args__ = (UniqueConstraint("app_id", "name", name="uq_build_configs_app_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_id: Mapped[int] = mapped_column(Integer, ForeignKey("apps.id"), nullable=False)
    image_tag: Mapped[str] = mapped_column(String(255), nullable=False)
    context_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dockerfile_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    build_args_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_orion_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_orion_naive,
        onupdate=now_orion_naive,
        nullable=False,
    )
