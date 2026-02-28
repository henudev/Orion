from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from app.models import app as app_model  # noqa: F401
from app.models import build as build_model  # noqa: F401
from app.models import build_config as build_config_model  # noqa: F401
from app.models import deployment as deployment_model  # noqa: F401
from app.models import deployment_config as deployment_config_model  # noqa: F401
from app.models import environment as environment_model  # noqa: F401


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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_environments_table()
