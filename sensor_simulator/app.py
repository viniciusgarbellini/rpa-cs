"""Simulador de sensor IoT — substitui um broker MQTT no MVP.

Justificativa: instalar Mosquitto no docker-compose adicionaria complexidade
sem ganho pedagógico (o foco é RPA, não infra MQTT). Esse simulador HTTP
expõe a mesma semântica:

  GET /readings?since=ISO  → buffer de mensagens novas
  POST /ack body={ids:[...]} → consumidor confirma processamento
  GET /healthz             → health

Importante: este simulador propositalmente envia leituras com unidades
DIFERENTES das do legado (°F, kV, hp) — pra exercitar a normalização!
"""

from __future__ import annotations

import math
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="IoT Sensor Simulator (HTTP)")

ASSETS = ["MTR-001", "MTR-002", "MTR-003", "MTR-004"]

# Buffer thread-safe de mensagens não-confirmadas
_buffer: list[dict[str, Any]] = []
_lock = threading.Lock()
_seq = 0


def _make_msg() -> dict[str, Any]:
    """Gera mensagem sintética com unidades NÃO-SI propositalmente."""
    global _seq
    _seq += 1
    tag = random.choice(ASSETS)
    now = datetime.now(timezone.utc).isoformat()

    # 70% manda em unidades "estranhas" (°F, kV, hp) pra testar normalizer
    use_imperial = random.random() < 0.7
    if use_imperial:
        temp_f = random.uniform(95, 165)  # °F
        temp = round(temp_f, 2)
        temp_unit = "°F"
        voltage = round(random.uniform(0.38, 0.46), 4)  # kV
        voltage_unit = "kV"
        power_hp = random.uniform(60, 200)
        power = round(power_hp, 2)
        power_unit = "hp"
    else:
        temp = round(random.uniform(35, 90), 2)
        temp_unit = "°C"
        voltage = round(random.uniform(380, 460), 1)
        voltage_unit = "V"
        power = round(random.uniform(20, 160), 2)
        power_unit = "kW"

    vib = round(random.uniform(0.5, 6.0), 2)
    vib_unit = random.choice(["mm/s", "in/s"])
    if vib_unit == "in/s":
        vib = round(vib / 25.4, 4)

    # Anomalia ocasional (10%): vibração alta
    if random.random() < 0.10:
        vib = round(vib * 5, 2)

    return {
        "id": f"sim-{_seq:010d}",
        "asset_tag": tag,
        "timestamp": now,
        "temperature": temp,
        "temperature_unit": temp_unit,
        "vibration": vib,
        "vibration_unit": vib_unit,
        "current": round(random.uniform(20, 290), 2),
        "current_unit": "A",
        "voltage": voltage,
        "voltage_unit": voltage_unit,
        "power": power,
        "power_unit": power_unit,
        "rpm": int(random.uniform(1700, 3580)),
    }


def _producer_loop() -> None:
    """Thread em background: produz 1 mensagem por segundo."""
    while True:
        try:
            with _lock:
                _buffer.append(_make_msg())
                # tampão máximo: dropa as mais antigas se passar de 500
                if len(_buffer) > 500:
                    del _buffer[:100]
        except Exception:
            pass
        time.sleep(1.0)


@app.on_event("startup")
def _start_producer() -> None:
    t = threading.Thread(target=_producer_loop, daemon=True)
    t.start()


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "buffer_size": len(_buffer)}


@app.get("/readings")
def readings(since: str = "1970-01-01T00:00:00Z") -> list[dict[str, Any]]:
    with _lock:
        if since == "1970-01-01T00:00:00Z":
            return list(_buffer)
        return [m for m in _buffer if m["timestamp"] > since]


@app.post("/ack")
def ack(body: dict[str, Any]) -> dict[str, Any]:
    ids = set(body.get("ids", []))
    with _lock:
        before = len(_buffer)
        _buffer[:] = [m for m in _buffer if m["id"] not in ids]
        after = len(_buffer)
    return {"acked": before - after, "remaining": after}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("SENSOR_API_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
