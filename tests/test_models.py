"""Testes dos contratos Pydantic (validação na fronteira)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.asset import Asset, AssetReadingClean, AssetReadingRaw


class TestAsset:
    def test_minimal_valid(self):
        a = Asset(tag="MTR-001", name="Motor 1")
        assert a.status == "ACTIVE"

    def test_tag_lowercase_rejected(self):
        with pytest.raises(ValidationError):
            Asset(tag="mtr-001", name="Motor 1")

    def test_negative_power_rejected(self):
        with pytest.raises(ValidationError):
            Asset(tag="MTR-001", name="Motor 1", rated_power_kw=-10)

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            Asset(tag="MTR-001", name="Motor 1", status="ZOMBIE")  # type: ignore[arg-type]


class TestReadings:
    def test_raw_reading_requires_source_id(self):
        with pytest.raises(ValidationError):
            AssetReadingRaw(
                asset_tag="MTR-001",
                source="file",
                payload={},
                received_at=datetime.now(timezone.utc),
                run_id=uuid4(),
            )  # type: ignore[call-arg]

    def test_clean_reading_score_bounds(self):
        with pytest.raises(ValidationError):
            AssetReadingClean(
                raw_id=1, asset_tag="MTR-001",
                measured_at=datetime.now(timezone.utc),
                quality_score=1.5,  # fora de [0,1]
            )

    def test_clean_reading_temperature_bounds(self):
        with pytest.raises(ValidationError):
            AssetReadingClean(
                raw_id=1, asset_tag="MTR-001",
                measured_at=datetime.now(timezone.utc),
                quality_score=1.0,
                temperature_c=10_000,  # impossível
            )

    def test_invalid_source_rejected(self):
        with pytest.raises(ValidationError):
            AssetReadingRaw(
                asset_tag="MTR-001",
                source="email",  # type: ignore[arg-type]
                source_id="x",
                payload={},
                received_at=datetime.now(timezone.utc),
                run_id=uuid4(),
            )
