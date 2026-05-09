"""Pydantic models — contratos de dados validados.

Garantem integridade na fronteira (entrada externa → sistema): qualquer
dado bruto é forçado por estes schemas antes de tocar o banco.
"""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceLiteral = Literal["file", "legacy_api", "sensor_iot", "manual"]
StatusLiteral = Literal["ACTIVE", "INACTIVE", "MAINTENANCE"]


class Asset(BaseModel):
    """Cadastro mestre de um motor elétrico."""

    model_config = ConfigDict(str_strip_whitespace=True)

    tag: str = Field(min_length=3, max_length=50, pattern=r"^[A-Z0-9\-_]+$")
    name: str = Field(min_length=3, max_length=200)
    manufacturer: str | None = None
    model: str | None = None
    rated_power_kw: float | None = Field(default=None, ge=0, le=10_000)
    rated_voltage_v: float | None = Field(default=None, ge=0, le=100_000)
    rated_current_a: float | None = Field(default=None, ge=0, le=10_000)
    rated_rpm: int | None = Field(default=None, ge=0, le=100_000)
    location: str | None = None
    installation_date: date | None = None
    status: StatusLiteral = "ACTIVE"


class AssetReadingRaw(BaseModel):
    """Leitura bruta — payload original direto da fonte."""

    asset_tag: str
    source: SourceLiteral
    source_id: str  # ID único na fonte (linha do CSV, msg_id do sensor, etc)
    payload: dict[str, Any]
    received_at: datetime
    run_id: UUID


class AssetReadingClean(BaseModel):
    """Leitura normalizada em SI (°C, V, A, kW, mm/s, rpm)."""

    raw_id: int
    asset_tag: str
    asset_id: int | None = None
    measured_at: datetime
    temperature_c: float | None = Field(default=None, ge=-50, le=300)
    vibration_mm_s: float | None = Field(default=None, ge=0, le=200)
    current_a: float | None = Field(default=None, ge=0, le=10_000)
    voltage_v: float | None = Field(default=None, ge=0, le=100_000)
    rpm: int | None = Field(default=None, ge=0, le=100_000)
    power_kw: float | None = Field(default=None, ge=0, le=10_000)
    quality_score: float = Field(ge=0, le=1)
    flags: dict[str, Any] = Field(default_factory=dict)

    @field_validator("flags", mode="before")
    @classmethod
    def _flags_default(cls, v: Any) -> dict[str, Any]:
        return v or {}


class ExecutionLog(BaseModel):
    """Log estruturado de uma execução de bot RPA."""

    run_id: UUID
    bot_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["RUNNING", "SUCCESS", "FAILED", "PARTIAL"]
    records_in: int = 0
    records_ok: int = 0
    records_failed: int = 0
    duration_ms: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
