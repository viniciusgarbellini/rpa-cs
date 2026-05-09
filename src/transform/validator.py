"""Validação + scoring de qualidade.

A normalização produz dados em SI mas pode haver:
  - campos faltando (sensor offline, planilha incompleta)
  - valores fora de faixa (ruído, defeito de sensor)
  - timestamp ausente

Esta camada classifica essas situações em FLAGS e atribui um quality_score
[0, 1] usado depois pra filtrar dados ruins em análises do Digital Twin.
"""

from datetime import datetime, timezone
from typing import Any


# Faixas operacionais típicas de motores industriais (dimensionadas com folga).
# Valores fora geram flag "out_of_range" mas NÃO descartam — só penalizam score.
RANGES = {
    "temperature_c":  (-20.0, 200.0),
    "vibration_mm_s": (0.0,   100.0),
    "current_a":      (0.0,   5_000.0),
    "voltage_v":      (0.0,   50_000.0),
    "rpm":            (0,     50_000),
    "power_kw":       (0.0,   5_000.0),
}

REQUIRED = {"measured_at"}
NUMERIC_FIELDS = {"temperature_c", "vibration_mm_s", "current_a", "voltage_v", "rpm", "power_kw"}


def validate_and_score(normalized: dict[str, Any]) -> dict[str, Any]:
    """Recebe o dict normalizado, devolve mesmo dict + flags + quality_score.

    Mutaciona e retorna o input por conveniência.
    """
    flags: dict[str, list[str]] = {
        "missing": [],
        "out_of_range": [],
        "errors": list(normalized.get("conversion_errors") or []),
    }

    # Campos obrigatórios ausentes
    for k in REQUIRED:
        if normalized.get(k) is None:
            flags["missing"].append(k)

    # Pelo menos UM campo numérico deve existir, senão a leitura é vazia
    present_numeric = [k for k in NUMERIC_FIELDS if normalized.get(k) is not None]
    if not present_numeric:
        flags["missing"].append("all_numeric_fields")

    # Range checks
    for field, (lo, hi) in RANGES.items():
        val = normalized.get(field)
        if val is None:
            continue
        if val < lo or val > hi:
            flags["out_of_range"].append(field)

    # Timestamp futuro (relógio descalibrado / payload corrompido)
    ts = normalized.get("measured_at")
    if isinstance(ts, datetime):
        now = datetime.now(timezone.utc)
        if ts > now:
            flags["errors"].append("future_timestamp")

    # ---------------------- score [0..1] ---------------------------
    # Heurística simples e auditável:
    #   começa em 1.0
    #   -0.3 por campo obrigatório ausente
    #   -0.1 por campo fora de faixa
    #   -0.2 por erro de conversão
    score = 1.0
    score -= 0.3 * len(flags["missing"])
    score -= 0.1 * len(flags["out_of_range"])
    score -= 0.2 * len(flags["errors"])
    score = max(0.0, min(1.0, score))

    normalized["flags"] = {k: v for k, v in flags.items() if v}
    normalized["quality_score"] = round(score, 2)
    normalized.pop("conversion_errors", None)
    return normalized
