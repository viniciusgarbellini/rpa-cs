"""ManualBot — RPA de leitura de planilhas Excel preenchidas por humanos.

Cenário típico de RPA: o operador anota leituras de campo numa planilha
(ex: ronda de manutenção semanal). O bot a varre e ingere.

Lê todos os .xlsx em data/manual/ e processa células preenchidas.
Diferente do FileBot, NÃO arquiva (a planilha é viva, atualizada periodicamente)
— a idempotência via UNIQUE(source, source_id) cuida de não duplicar.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

import openpyxl

from src.bots.base import BaseBot
from src.config import settings
from src.models.asset import AssetReadingRaw


class ManualBot(BaseBot):
    name = "manual_bot"
    source = "manual"

    EXPECTED_COLUMNS = [
        "asset_tag", "timestamp", "temperature", "temperature_unit",
        "vibration", "vibration_unit", "current", "current_unit",
        "voltage", "voltage_unit", "rpm", "operator",
    ]

    def __init__(self, manual_dir: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.manual_dir = manual_dir or settings.manual_folder
        self.manual_dir.mkdir(parents=True, exist_ok=True)

    def extract(self) -> Iterable[dict[str, Any]]:
        for fpath in sorted(self.manual_dir.glob("*.xlsx")):
            wb = openpyxl.load_workbook(fpath, data_only=True, read_only=True)
            for sheet in wb.worksheets:
                rows = sheet.iter_rows(values_only=True)
                header = next(rows, None)
                if not header:
                    continue
                header_norm = [str(c).strip().lower() if c else "" for c in header]
                for line_no, row in enumerate(rows, start=2):
                    if all(v is None or v == "" for v in row):
                        continue
                    rec = dict(zip(header_norm, row))
                    rec["_file"] = fpath.name
                    rec["_sheet"] = sheet.title
                    rec["_line"] = line_no
                    yield rec
            wb.close()

    def parse(self, record: dict[str, Any], run_id: UUID) -> AssetReadingRaw:
        tag = (record.get("asset_tag") or "").strip().upper() if isinstance(record.get("asset_tag"), str) else None
        if not tag:
            raise ValueError("asset_tag ausente na linha da planilha")

        source_id = f"{record['_file']}:{record['_sheet']}:L{record['_line']}"

        payload: dict[str, Any] = {}
        for k, v in record.items():
            if k.startswith("_") or v is None or v == "":
                continue
            if isinstance(v, datetime):
                payload[k] = v.isoformat()
            else:
                payload[k] = v

        return AssetReadingRaw(
            asset_tag=tag,
            source=self.source,
            source_id=source_id,
            payload=payload,
            received_at=datetime.now(timezone.utc),
            run_id=run_id,
        )
