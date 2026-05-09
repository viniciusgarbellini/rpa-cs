"""FileBot — RPA clássico de "drop folder".

Comportamento típico de RPA de arquivo:
  1. Varre uma pasta de drop (data/drop/)
  2. Lê cada CSV encontrado
  3. Processa todas as linhas
  4. Move o arquivo pra pasta archive/ com timestamp
  5. Em caso de erro de leitura, marca como .failed e arquiva separado

Cada CSV é tratado como uma "remessa" do PCM/manutenção.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from src.bots.base import BaseBot
from src.config import settings
from src.models.asset import AssetReadingRaw


class FileBot(BaseBot):
    name = "file_bot"
    source = "file"

    def __init__(self, drop_dir: Path | None = None, archive_dir: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.drop_dir = drop_dir or settings.drop_folder
        self.archive_dir = archive_dir or settings.archive_folder
        self.drop_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._current_file: Path | None = None

    def extract(self) -> Iterable[dict[str, Any]]:
        files = sorted(self.drop_dir.glob("*.csv"))
        for fpath in files:
            self._current_file = fpath
            try:
                with fpath.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for line_no, row in enumerate(reader, start=2):  # header é linha 1
                        row["_file"] = fpath.name
                        row["_line"] = line_no
                        yield row
                self._archive(fpath, success=True)
            except Exception as e:
                self._archive(fpath, success=False, reason=str(e))
                raise

    def parse(self, record: dict[str, Any], run_id: UUID) -> AssetReadingRaw:
        tag = (record.get("asset_tag") or record.get("tag") or "").strip().upper()
        if not tag:
            raise ValueError("asset_tag ausente na linha do CSV")

        # source_id estável por arquivo+linha → idempotência
        source_id = f"{record['_file']}:L{record['_line']}"

        # Remove os campos meta antes de persistir
        payload = {k: v for k, v in record.items() if not k.startswith("_") and v != ""}

        return AssetReadingRaw(
            asset_tag=tag,
            source=self.source,
            source_id=source_id,
            payload=payload,
            received_at=datetime.now(timezone.utc),
            run_id=run_id,
        )

    # ---------------- helpers --------------------------------------------

    def _archive(self, fpath: Path, success: bool, reason: str = "") -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        suffix = "" if success else ".failed"
        target = self.archive_dir / f"{fpath.stem}.{ts}{suffix}{fpath.suffix}"
        try:
            fpath.rename(target)
        except OSError:
            # Em Windows, se travado, copia + remove
            target.write_bytes(fpath.read_bytes())
            fpath.unlink(missing_ok=True)

        if not success and reason:
            (target.with_suffix(target.suffix + ".reason.txt")).write_text(
                reason, encoding="utf-8"
            )
