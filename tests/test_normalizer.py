"""Testes da camada de normalização (conversão de unidades)."""

from datetime import datetime, timezone

import pytest

from src.transform.normalizer import (
    normalize_payload,
    parse_timestamp,
    to_amperes,
    to_celsius,
    to_kw,
    to_mm_s,
    to_volts,
)


class TestUnitConversions:
    def test_celsius_passthrough(self):
        assert to_celsius(25.0, "°C") == 25.0
        assert to_celsius(25.0, "celsius") == 25.0

    def test_fahrenheit_to_celsius(self):
        assert to_celsius(32.0, "°F") == pytest.approx(0.0)
        assert to_celsius(212.0, "°F") == pytest.approx(100.0)

    def test_kelvin_to_celsius(self):
        assert to_celsius(273.15, "K") == pytest.approx(0.0, abs=1e-6)

    def test_unknown_temperature_unit_raises(self):
        with pytest.raises(ValueError):
            to_celsius(25.0, "rankine")

    def test_kilovolts_to_volts(self):
        assert to_volts(0.44, "kV") == pytest.approx(440.0)

    def test_milliamperes_to_amperes(self):
        assert to_amperes(500.0, "mA") == 0.5

    def test_horsepower_to_kw(self):
        # 100 hp ≈ 74.57 kW
        assert to_kw(100.0, "hp") == pytest.approx(74.57)

    def test_megawatt_to_kw(self):
        assert to_kw(1.0, "MW") == 1000.0

    def test_in_per_second_to_mm_per_second(self):
        assert to_mm_s(1.0, "in/s") == pytest.approx(25.4)


class TestTimestampParsing:
    def test_iso_with_z(self):
        ts = parse_timestamp("2026-05-09T10:30:00Z")
        assert ts.tzinfo is not None
        assert ts.year == 2026

    def test_epoch_seconds(self):
        ts = parse_timestamp(1_700_000_000)
        assert isinstance(ts, datetime)
        assert ts.tzinfo == timezone.utc

    def test_epoch_milliseconds(self):
        ts = parse_timestamp(1_700_000_000_000)
        assert isinstance(ts, datetime)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_timestamp("not a date")


class TestNormalizePayload:
    def test_full_si_payload(self):
        payload = {
            "timestamp": "2026-05-09T10:00:00Z",
            "temperature": 50.0, "temperature_unit": "°C",
            "vibration": 2.5, "vibration_unit": "mm/s",
            "current": 100.0, "current_unit": "A",
            "voltage": 440.0, "voltage_unit": "V",
            "power": 50.0, "power_unit": "kW",
            "rpm": 1780,
        }
        out = normalize_payload(payload)
        assert out["temperature_c"] == 50.0
        assert out["vibration_mm_s"] == 2.5
        assert out["voltage_v"] == 440.0
        assert out["rpm"] == 1780
        assert out["conversion_errors"] == []

    def test_imperial_payload_converted(self):
        payload = {
            "timestamp": "2026-05-09T10:00:00Z",
            "temperature": 212.0, "temperature_unit": "°F",
            "voltage": 0.44, "voltage_unit": "kV",
            "power": 100.0, "power_unit": "hp",
        }
        out = normalize_payload(payload)
        assert out["temperature_c"] == pytest.approx(100.0)
        assert out["voltage_v"] == pytest.approx(440.0)
        assert out["power_kw"] == pytest.approx(74.57)
        assert out["conversion_errors"] == []

    def test_partial_payload_no_errors_for_missing(self):
        out = normalize_payload({"timestamp": "2026-05-09T10:00:00Z"})
        assert out["temperature_c"] is None
        assert out["conversion_errors"] == []

    def test_invalid_unit_recorded_as_error(self):
        out = normalize_payload({
            "timestamp": "2026-05-09T10:00:00Z",
            "temperature": 50, "temperature_unit": "rankine",
        })
        assert any("temperature" in e for e in out["conversion_errors"])

    def test_empty_payload_does_not_crash(self):
        out = normalize_payload({})
        assert out["measured_at"] is None
