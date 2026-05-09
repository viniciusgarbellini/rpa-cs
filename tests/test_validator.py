"""Testes da validação + scoring de qualidade."""

from datetime import datetime, timedelta, timezone

from src.transform.validator import validate_and_score


def _base():
    return {
        "measured_at": datetime.now(timezone.utc),
        "temperature_c": 60.0,
        "vibration_mm_s": 2.5,
        "current_a": 100.0,
        "voltage_v": 440.0,
        "rpm": 1780,
        "power_kw": 50.0,
        "conversion_errors": [],
    }


def test_perfect_payload_score_one():
    out = validate_and_score(_base())
    assert out["quality_score"] == 1.0
    assert out["flags"] == {}


def test_missing_measured_at_penalizes():
    p = _base()
    p["measured_at"] = None
    out = validate_and_score(p)
    assert "measured_at" in out["flags"]["missing"]
    assert out["quality_score"] < 1.0


def test_out_of_range_penalizes_but_keeps_value():
    p = _base()
    p["temperature_c"] = 500.0  # absurdo
    out = validate_and_score(p)
    assert "temperature_c" in out["flags"]["out_of_range"]
    assert out["temperature_c"] == 500.0


def test_future_timestamp_flagged():
    p = _base()
    p["measured_at"] = datetime.now(timezone.utc) + timedelta(days=1)
    out = validate_and_score(p)
    assert "future_timestamp" in out["flags"]["errors"]


def test_all_numeric_missing_marks_payload_empty():
    p = {
        "measured_at": datetime.now(timezone.utc),
        "temperature_c": None, "vibration_mm_s": None,
        "current_a": None, "voltage_v": None, "rpm": None, "power_kw": None,
        "conversion_errors": [],
    }
    out = validate_and_score(p)
    assert "all_numeric_fields" in out["flags"]["missing"]


def test_score_clamped_to_zero():
    p = _base()
    p["measured_at"] = None
    p["temperature_c"] = None
    p["vibration_mm_s"] = None
    p["current_a"] = None
    p["voltage_v"] = None
    p["rpm"] = None
    p["power_kw"] = None
    p["conversion_errors"] = ["x", "y", "z", "w"]
    out = validate_and_score(p)
    assert 0.0 <= out["quality_score"] <= 1.0
