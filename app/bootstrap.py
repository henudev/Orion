from __future__ import annotations

from app.core.config import settings
from app.db.init_db import init_db
from app.services.path_manager import ensure_orion_layout


def bootstrap() -> None:
    ensure_orion_layout()
    init_db()
    print(f"Orion initialized at: {settings.orion_home}")
    print(f"SQLite database: {settings.database_path}")


if __name__ == "__main__":
    bootstrap()

