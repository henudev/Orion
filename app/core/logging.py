from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.timezone import get_orion_tz, now_orion


class OrionTimezoneFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=get_orion_tz())
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def _get_daily_logger(kind: str) -> logging.Logger:
    date_part = now_orion().strftime("%Y-%m-%d")
    logger_name = f"orion.{kind}.{date_part}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.logs_dir / f"{kind}-{date_part}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(OrionTimezoneFormatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def get_daily_log_file(kind: str) -> Path:
    return settings.logs_dir / f"{kind}-{now_orion().strftime('%Y-%m-%d')}.log"


def write_build_log(build_id: int, message: str) -> None:
    logger = _get_daily_logger("build")
    logger.info("[BUILD_ID=%s] %s", build_id, message)


def write_deploy_log(deployment_id: int, message: str) -> None:
    logger = _get_daily_logger("deploy")
    logger.info("[DEPLOY_ID=%s] %s", deployment_id, message)
