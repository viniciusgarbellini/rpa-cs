"""SensorBot — RPA de coleta de sensores IoT.

O simulador (sensor_simulator/) expõe um endpoint HTTP que devolve o buffer
acumulado desde a última leitura (modelo "pull" simplificado de um broker MQTT).

Endpoint:
  GET /readings?since=ISO → lista de leituras do "buffer"
  POST /ack  body={ids: [...]} → marca como consumidas (at-least-once)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
)

from src.bots.base import BaseBot
from src.config import settings
from src.models.asset import AssetReadingRaw


class SensorBot(BaseBot):
    name = "sensor_bot"
    source = "sensor_iot"

    def __init__(self, base_url: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = (base_url or settings.sensor_api_url).rstrip("/")
        self._consumed_ids: list[str] = []
        self._since: str = "1970-01-01T00:00:00Z"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=5),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _get(self, path: str, **params) -> Any:
        r = requests.get(f"{self.base_url}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: Any) -> None:
        r = requests.post(f"{self.base_url}{path}", json=json, timeout=10)
        r.raise_for_status()

    def extract(self) -> Iterable[dict[str, Any]]:
        readings = self._get("/readings", since=self._since)
        for msg in readings:
            yield msg
            mid = msg.get("id")
            if mid:
                self._consumed_ids.append(str(mid))
            ts = msg.get("timestamp")
            if ts and ts > self._since:
                self._since = ts

        # ACK ao final do batch (at-least-once: se cair antes daqui,
        # reprocessamos no próximo run, mas readings_raw é idempotente)
        if self._consumed_ids:
            try:
                self._post("/ack", json={"ids": self._consumed_ids})
            except requests.RequestException:
                pass  # ack falhou — vamos reler, mas idempotência protege
            finally:
                self._consumed_ids = []

    def parse(self, record: dict[str, Any], run_id: UUID) -> AssetReadingRaw:
        tag = (record.get("asset_tag") or "").upper()
        if not tag:
            raise ValueError("asset_tag ausente na mensagem do sensor")
        mid = record.get("id")
        if not mid:
            raise ValueError("message id ausente — sem chave de idempotência")

        return AssetReadingRaw(
            asset_tag=tag,
            source=self.source,
            source_id=f"sensor:{mid}",
            payload=record,
            received_at=datetime.now(timezone.utc),
            run_id=run_id,
        )
