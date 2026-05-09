"""ApiBot — RPA de integração com sistema legado via REST.

Simula o cenário típico onde o sistema antigo de cadastro/PCM expõe uma API
e o RPA precisa periodicamente puxar atualizações (pull batch).

A API mock (legacy_api/app.py) entrega:
  - GET /assets         → cadastro de motores (com status/manutenção)
  - GET /assets/{tag}/readings?since=ISO → leituras desde o último pull
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
from src.models.asset import Asset, AssetReadingRaw


class ApiBot(BaseBot):
    name = "api_bot"
    source = "legacy_api"

    def __init__(self, base_url: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = (base_url or settings.legacy_api_url).rstrip("/")
        self._last_seen: dict[str, str] = {}  # tag → ISO timestamp

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

    def extract(self) -> Iterable[dict[str, Any]]:
        # 1) Sincroniza cadastro
        assets_payload = self._get("/assets")
        for a in assets_payload:
            try:
                asset = Asset(**a)
                self.repo.upsert_asset(asset, changed_by=self.name, reason="sync_legacy")
            except Exception as e:  # validação Pydantic falhou → ignora cadastro mas loga
                yield {"_skip": True, "_error": f"asset cadastro inválido: {e!r}"}

        # 2) Puxa leituras incrementais por ativo
        for a in assets_payload:
            tag = a.get("tag")
            if not tag:
                continue
            since = self._last_seen.get(tag, "1970-01-01T00:00:00Z")
            readings = self._get(f"/assets/{tag}/readings", since=since)
            for r in readings:
                r["_tag"] = tag
                yield r
                ts = r.get("timestamp")
                if ts and ts > since:
                    self._last_seen[tag] = ts

    def parse(self, record: dict[str, Any], run_id: UUID) -> AssetReadingRaw:
        if record.get("_skip"):
            raise ValueError(record.get("_error", "skip"))
        tag = record.pop("_tag", None) or record.get("asset_tag")
        if not tag:
            raise ValueError("asset_tag ausente no payload da API")

        msg_id = record.get("id") or record.get("message_id")
        if not msg_id:
            raise ValueError("id/message_id ausente — sem chave de idempotência")

        return AssetReadingRaw(
            asset_tag=str(tag).upper(),
            source=self.source,
            source_id=f"{tag}:{msg_id}",
            payload=record,
            received_at=datetime.now(timezone.utc),
            run_id=run_id,
        )
