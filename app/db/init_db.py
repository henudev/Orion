from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from app.models import app as app_model  # noqa: F401
from app.models import build as build_model  # noqa: F401
from app.models import build_config as build_config_model  # noqa: F401
from app.models import deployment as deployment_model  # noqa: F401
from app.models import deployment_config as deployment_config_model  # noqa: F401
from app.models import environment as environment_model  # noqa: F401
from app.models import model_config as model_config_model  # noqa: F401

_MIGRATION_TZ_CST_V1 = "20260303_timezone_to_utc_plus_8_v1"
_TIMESTAMP_COLUMNS: dict[str, tuple[str, ...]] = {
    "apps": ("created_at",),
    "environments": ("created_at",),
    "builds": ("created_at",),
    "deployments": ("created_at",),
    "build_configs": ("created_at", "updated_at"),
    "deployment_configs": ("created_at", "updated_at"),
    "model_configs": ("created_at", "updated_at"),
}


def _migrate_environments_table() -> None:
    inspector = inspect(engine)
    if "environments" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("environments")}
    with engine.begin() as conn:
        if "password" not in columns:
            conn.execute(text("ALTER TABLE environments ADD COLUMN password TEXT NOT NULL DEFAULT ''"))
        if "ssh_key_path" not in columns:
            conn.execute(text("ALTER TABLE environments ADD COLUMN ssh_key_path TEXT NOT NULL DEFAULT ''"))


def _ensure_migrations_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
        )


def _has_migration(name: str) -> bool:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT 1 FROM schema_migrations WHERE name = :name"), {"name": name}).first()
    return row is not None


def _mark_migration(name: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO schema_migrations(name, applied_at) "
                "VALUES(:name, strftime('%Y-%m-%d %H:%M:%f', 'now', '+8 hours'))"
            ),
            {"name": name},
        )


def _migrate_naive_utc_to_utc_plus_8() -> None:
    _ensure_migrations_table()
    if _has_migration(_MIGRATION_TZ_CST_V1):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table_name, columns in _TIMESTAMP_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name in columns:
                if column_name not in existing_columns:
                    continue
                conn.execute(
                    text(
                        f"UPDATE {table_name} "
                        f"SET {column_name} = strftime('%Y-%m-%d %H:%M:%f', {column_name}, '+8 hours') "
                        f"WHERE {column_name} IS NOT NULL"
                    )
                )

    _mark_migration(_MIGRATION_TZ_CST_V1)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_environments_table()
    _migrate_naive_utc_to_utc_plus_8()
