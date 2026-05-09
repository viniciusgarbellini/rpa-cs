"""Normalização de unidades — converte payloads heterogêneos pra SI.

Cada fonte tem um vocabulário próprio (sensor manda °F, planilha em °C, API
manda kelvin). Aqui homogeneizamos: todas as leituras saem em (°C, V, A, kW,
mm/s, rpm) — a base canônica do Digital Twin.
"""

from datetime import datetime, timezone
from typing import Any


# ----------------------- conversões individuais ------------------------------

def to_celsius(value: float, unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"c", "°c", "celsius"}:
        return float(value)
    if u in {"f", "°f", "fahrenheit"}:
        return (float(value) - 32.0) * 5.0 / 9.0
    if u in {"k", "kelvin"}:
        return float(value) - 273.15
    raise ValueError(f"Unidade de temperatura desconhecida: {unit!r}")


def to_volts(value: float, unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"v", "volt", "volts"}:
        return float(value)
    if u in {"kv", "kilovolt", "kilovolts"}:
        return float(value) * 1_000.0
    if u in {"mv", "millivolt", "millivolts"}:
        return float(value) / 1_000.0
    raise ValueError(f"Unidade de tensão desconhecida: {unit!r}")


def to_amperes(value: float, unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"a", "amp", "ampere", "amperes"}:
        return float(value)
    if u in {"ma", "milliamp", "milliamperes"}:
        return float(value) / 1_000.0
    raise ValueError(f"Unidade de corrente desconhecida: {unit!r}")


def to_kw(value: float, unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"kw", "kilowatt", "kilowatts"}:
        return float(value)
    if u in {"w", "watt", "watts"}:
        return float(value) / 1_000.0
    if u in {"hp", "cv"}:  # cavalo-vapor / horsepower (aprox)
        return float(value) * 0.7457
    if u in {"mw", "megawatt", "megawatts"}:
        return float(value) * 1_000.0
    raise ValueError(f"Unidade de potência desconhecida: {unit!r}")


def to_mm_s(value: float, unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"mm/s", "mm_s", "mms"}:
        return float(value)
    if u in {"m/s", "m_s"}:
        return float(value) * 1_000.0
    if u in {"in/s", "ips"}:
        return float(value) * 25.4
    raise ValueError(f"Unidade de vibração desconhecida: {unit!r}")


def parse_timestamp(value: Any) -> datetime:
    """Aceita ISO 8601 string ou epoch (s/ms) e devolve datetime tz-aware UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # Heurística: se > 1e12, é em milissegundos
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        # ISO 8601 com 'Z' ou offset
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"Timestamp inválido: {value!r}")


# ----------------------- normalização principal ------------------------------

def _get(payload: dict[str, Any], *keys: str) -> Any:
    """Pega o primeiro valor existente entre as chaves candidatas."""
    for k in keys:
        if k in payload and payload[k] is not None:
            return payload[k]
    return None


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normaliza um payload heterogêneo pra dict SI canônico.

    Espera (mas tolera ausência de) os campos:
      timestamp, temperature{,_unit}, vibration{,_unit}, current{,_unit},
      voltage{,_unit}, power{,_unit}, rpm.

    Retorna dict com chaves: measured_at, temperature_c, vibration_mm_s,
    current_a, voltage_v, rpm, power_kw, conversion_errors (lista de strings).
    """
    errors: list[str] = []
    out: dict[str, Any] = {
        "measured_at": None,
        "temperature_c": None,
        "vibration_mm_s": None,
        "current_a": None,
        "voltage_v": None,
        "rpm": None,
        "power_kw": None,
        "conversion_errors": errors,
    }

    ts = _get(payload, "timestamp", "measured_at", "ts", "time")
    if ts is not None:
        try:
            out["measured_at"] = parse_timestamp(ts)
        except (ValueError, TypeError) as e:
            errors.append(f"timestamp: {e}")

    pairs = [
        ("temperature_c", "temperature", "temperature_unit", "°C", to_celsius),
        ("vibration_mm_s", "vibration", "vibration_unit", "mm/s", to_mm_s),
        ("current_a", "current", "current_unit", "A", to_amperes),
        ("voltage_v", "voltage", "voltage_unit", "V", to_volts),
        ("power_kw", "power", "power_unit", "kW", to_kw),
    ]

    for out_key, val_key, unit_key, default_unit, fn in pairs:
        val = _get(payload, val_key)
        if val is None:
            continue
        unit = _get(payload, unit_key) or default_unit
        try:
            out[out_key] = round(fn(float(val), str(unit)), 4)
        except (ValueError, TypeError) as e:
            errors.append(f"{out_key}: {e}")

    rpm = _get(payload, "rpm", "speed", "rotation")
    if rpm is not None:
        try:
            out["rpm"] = int(float(rpm))
        except (ValueError, TypeError) as e:
            errors.append(f"rpm: {e}")

    return out
