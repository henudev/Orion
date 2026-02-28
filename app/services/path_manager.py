from __future__ import annotations

from pathlib import Path

from app.core.config import settings


def required_paths() -> list[Path]:
    return [
        settings.orion_home,
        settings.workspace_dir,
        settings.builds_dir,
        settings.logs_dir,
        settings.artifacts_images_dir,
        settings.compose_dir,
        settings.runtime_dir,
        settings.backups_dir,
        settings.database_dir,
    ]


def ensure_orion_layout() -> None:
    for path in required_paths():
        path.mkdir(parents=True, exist_ok=True)

