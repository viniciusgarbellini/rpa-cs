"""Configuração centralizada via variáveis de ambiente (12-factor app)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "rpa_assets"
    postgres_user: str = "rpa"
    postgres_password: str = "rpa_secret_change_me"

    # Aplicação
    app_env: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"

    # Mock APIs
    legacy_api_url: str = "http://localhost:8001"
    sensor_api_url: str = "http://localhost:8002"

    # Schedules (cron-style: m h dom mon dow)
    schedule_file_bot: str = "*/2 * * * *"
    schedule_api_bot: str = "*/3 * * * *"
    schedule_sensor_bot: str = "*/1 * * * *"
    schedule_manual_bot: str = "*/5 * * * *"

    # Paths
    drop_folder: Path = Path("./data/drop")
    archive_folder: Path = Path("./data/archive")
    manual_folder: Path = Path("./data/manual")
    log_folder: Path = Path("./logs")

    @property
    def db_dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password}"
        )


settings = Settings()
