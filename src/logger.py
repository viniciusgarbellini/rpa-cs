"""Logger estruturado (JSON) com Loguru.

Toda automação RPA produz logs com:
  - run_id (UUID por execução)
  - bot_name
  - level, time, message
  - context extra arbitrário

Saída dupla:
  - stdout (capturado pelo Docker)
  - arquivo rotacionado em ./logs/rpa.log
"""

import sys
from pathlib import Path

from loguru import logger

from src.config import settings


def setup_logger() -> None:
    """Configura Loguru com saída JSON (stdout + arquivo rotacionado)."""
    logger.remove()

    settings.log_folder.mkdir(parents=True, exist_ok=True)

    is_json = settings.log_format.lower() == "json"

    fmt = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{extra[bot]:<12} | run={extra[run_id]} | {message}"
    )

    logger.configure(extra={"bot": "system", "run_id": "-"})

    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=fmt,
        serialize=is_json,
        backtrace=True,
        diagnose=False,
    )

    logger.add(
        settings.log_folder / "rpa.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        serialize=True,  # arquivo SEMPRE em JSON pra parse posterior
        enqueue=True,
    )


def get_logger(bot_name: str, run_id: str | None = None):
    """Retorna logger contextualizado pra um bot/execução."""
    return logger.bind(bot=bot_name, run_id=run_id or "-")
