from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "Orion猎户座"
    api_prefix: str = "/api"
    timezone_name: str = os.getenv("ORION_TIMEZONE", "Asia/Shanghai")
    max_concurrent_builds: int = int(os.getenv("MAX_CONCURRENT_BUILDS", "2"))
    build_retry_limit: int = int(os.getenv("BUILD_RETRY_LIMIT", "2"))
    build_timeout_seconds: int = int(os.getenv("BUILD_TIMEOUT_SECONDS", "1800"))
    deploy_timeout_seconds: int = int(os.getenv("DEPLOY_TIMEOUT_SECONDS", "1800"))

    orion_home: Path = Path(os.getenv("ORION_HOME", str(Path.home() / "Orion"))).expanduser()

    @property
    def workspace_dir(self) -> Path:
        return self.orion_home / "workspace"

    @property
    def builds_dir(self) -> Path:
        return self.orion_home / "builds"

    @property
    def logs_dir(self) -> Path:
        return self.orion_home / "logs"

    @property
    def artifacts_images_dir(self) -> Path:
        return self.orion_home / "artifacts" / "images"

    @property
    def compose_dir(self) -> Path:
        return self.orion_home / "compose"

    @property
    def runtime_dir(self) -> Path:
        return self.orion_home / "runtime"

    @property
    def backups_dir(self) -> Path:
        return self.orion_home / "backups"

    @property
    def database_dir(self) -> Path:
        return self.orion_home / "database"

    @property
    def database_path(self) -> Path:
        return self.database_dir / "orion.db"


settings = Settings()
