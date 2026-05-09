"""Mock do sistema legado: cadastro de motores + leituras periódicas.

Justificativa: o enunciado pede coleta de "sistemas legados". Construímos
um mock realista (FastAPI) que devolve cadastro + leituras incrementais,
permitindo que o ApiBot exercite o cenário completo sem dependência externa.

Endpoints:
  GET  /assets                          → cadastro completo dos motores
  GET  /assets/{tag}/readings?since=ISO → leituras desde o timestamp informado
  GET  /healthz                         → health check do container

Os dados são gerados em memória, com leituras novas sendo "produzidas"
a cada chamada (simulando que o sistema está ativo).
"""

from __future__ import annotations

import math
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Legacy Asset Management API (mock)")

# -------------------- cadastro fixo (cenário industrial real) ----------------

ASSETS: list[dict[str, Any]] = [
    {
        "tag": "MTR-001",
        "name": "Motor Bomba Centrífuga 01",
        "manufacturer": "WEG",
        "model": "W22 IR3",
        "rated_power_kw": 75.0,
        "rated_voltage_v": 440.0,
        "rated_current_a": 130.0,
        "rated_rpm": 3550,
        "location": "Linha 1 - Bombeamento",
        "installation_date": "2019-05-12",
        "status": "ACTIVE",
    },
    {
        "tag": "MTR-002",
        "name": "Motor Compressor Parafuso 02",
        "manufacturer": "Atlas Copco",
        "model": "GA-160",
        "rated_power_kw": 160.0,
        "rated_voltage_v": 440.0,
        "rated_current_a": 280.0,
        "rated_rpm": 1780,
        "location": "Casa de Compressores",
        "installation_date": "2020-09-03",
        "status": "ACTIVE",
    },
    {
        "tag": "MTR-003",
        "name": "Motor Esteira Transportadora 03",
        "manufacturer": "Siemens",
        "model": "SIMOTICS GP",
        "rated_power_kw": 22.0,
        "rated_voltage_v": 380.0,
        "rated_current_a": 42.0,
        "rated_rpm": 1750,
        "location": "Linha 2 - Conveyor",
        "installation_date": "2018-02-20",
        "status": "MAINTENANCE",
    },
    {
        "tag": "MTR-004",
        "name": "Motor Ventilador Industrial 04",
        "manufacturer": "WEG",
        "model": "W22 IR4",
        "rated_power_kw": 45.0,
        "rated_voltage_v": 440.0,
        "rated_current_a": 80.0,
        "rated_rpm": 1185,
        "location": "Casa de Máquinas - Exaustão",
        "installation_date": "2021-11-15",
        "status": "ACTIVE",
    },
]


# -------------------- gerador de leituras (legado em °C, V, A, kW) -----------

_seq = {a["tag"]: 0 for a in ASSETS}


def _gen_reading(asset: dict[str, Any], when: datetime) -> dict[str, Any]:
    _seq[asset["tag"]] += 1
    rated_a = asset["rated_current_a"]
    rated_v = asset["rated_voltage_v"]
    rated_kw = asset["rated_power_kw"]

    # Variação realista em torno do nominal
    load = random.uniform(0.55, 0.95)
    current = rated_a * load * random.uniform(0.95, 1.05)
    voltage = rated_v * random.uniform(0.97, 1.03)
    power = rated_kw * load * random.uniform(0.92, 1.05)
    temp = 35 + 30 * load + random.uniform(-3, 3)
    vib = 1.5 + load * 2 + random.uniform(-0.4, 0.4)

    # 5% de chance de injetar anomalia (testar flags out_of_range)
    if random.random() < 0.05:
        temp += random.uniform(80, 120)

    return {
        "id": f"{asset['tag']}-{_seq[asset['tag']]:08d}",
        "asset_tag": asset["tag"],
        "timestamp": when.isoformat(),
        "temperature": round(temp, 2),
        "temperature_unit": "°C",
        "vibration": round(vib, 2),
        "vibration_unit": "mm/s",
        "current": round(current, 2),
        "current_unit": "A",
        "voltage": round(voltage, 1),
        "voltage_unit": "V",
        "power": round(power, 2),
        "power_unit": "kW",
        "rpm": int(asset["rated_rpm"] * random.uniform(0.96, 1.0)),
    }


# -------------------- endpoints ---------------------------------------------

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/assets")
def list_assets() -> list[dict[str, Any]]:
    return ASSETS


@app.get("/assets/{tag}/readings")
def get_readings(tag: str, since: str = "1970-01-01T00:00:00Z") -> list[dict[str, Any]]:
    asset = next((a for a in ASSETS if a["tag"].upper() == tag.upper()), None)
    if asset is None:
        raise HTTPException(404, f"Asset not found: {tag}")

    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"Invalid `since`: {since!r}")

    # Gera entre 5 e 12 leituras "desde" o último pull (espaçadas a cada 10s)
    now = datetime.now(timezone.utc)
    n = random.randint(5, 12)
    readings = []
    for i in range(n):
        t = now - timedelta(seconds=10 * (n - i))
        if t > since_dt:
            readings.append(_gen_reading(asset, t))
    return readings


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("LEGACY_API_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
