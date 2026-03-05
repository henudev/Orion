from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_orion_naive
from app.db.base import Base


class DeploymentConfig(Base):
    __tablename__ = "deployment_configs"
    __table_args__ = (
        UniqueConstraint("app_id", "environment_id", "name", name="uq_deploy_configs_app_env_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_id: Mapped[int] = mapped_column(Integer, ForeignKey("apps.id"), nullable=False)
    environment_id: Mapped[int] = mapped_column(Integer, ForeignKey("environments.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    build_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ports_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    env_vars_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    compose_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_orion_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_orion_naive,
        onupdate=now_orion_naive,
        nullable=False,
    )
