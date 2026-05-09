"""Conexão Postgres + bootstrap do schema.

psycopg3 com retry exponencial: o orquestrador sobe junto com o banco
no docker-compose, então a 1ª tentativa pode falhar (DB ainda iniciando).
"""

from contextlib import contextmanager
from pathlib import Path

import psycopg
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import settings
from src.logger import logger


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=15),
    retry=retry_if_exception_type(psycopg.OperationalError),
    reraise=True,
)
def _connect() -> psycopg.Connection:
    return psycopg.connect(settings.db_dsn)


@contextmanager
def get_connection():
    """Context manager pra obter conexão Postgres com auto-close."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Cria o schema (idempotente — usa CREATE IF NOT EXISTS)."""
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    logger.bind(bot="system", run_id="-").info("Schema inicializado")
