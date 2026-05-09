"""Base class para todos os bots RPA.

Padrão template-method:
  - run() abre uma execução, chama extract → process_record loop, fecha exec.
  - Cada subclasse implementa apenas extract() e parse(record) → AssetReadingRaw.

Garantias:
  - Toda execução é registrada em execution_logs (start/finish, status, contagens).
  - Erros em registros individuais NÃO derrubam o bot (PARTIAL).
  - Erro fatal de execução é capturado e registrado como FAILED.
  - Logs estruturados via Loguru com run_id em todo evento.
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from src.db.repository import Repository
from src.logger import get_logger
from src.models.asset import AssetReadingClean, AssetReadingRaw, ExecutionLog
from src.transform import normalize_payload, validate_and_score


class BaseBot(ABC):
    """Classe base de qualquer bot RPA do sistema."""

    name: str = "base"
    source: str = "file"  # file | legacy_api | sensor_iot | manual

    def __init__(self, repo: Repository | None = None):
        self.repo = repo or Repository()

    # ------------------ template-method ------------------------------------

    def run(self) -> ExecutionLog:
        run_id = uuid4()
        log = get_logger(self.name, str(run_id))
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()

        exec_log = ExecutionLog(
            run_id=run_id,
            bot_name=self.name,
            started_at=started,
            status="RUNNING",
        )
        try:
            self.repo.start_run(exec_log)
            log.info(f"[{self.name}] Execução iniciada")
        except Exception as e:
            log.exception(f"Falha registrando início: {e}")
            return exec_log

        records_in = ok = failed = 0

        try:
            for record in self.extract():
                records_in += 1
                try:
                    raw = self.parse(record, run_id=run_id)
                    self._process_record(raw, log)
                    ok += 1
                except Exception as e:
                    failed += 1
                    log.warning(f"Registro descartado: {e!r} :: record={record!r}")

            duration_ms = int((time.perf_counter() - t0) * 1000)
            status = "SUCCESS" if failed == 0 else ("PARTIAL" if ok > 0 else "FAILED")
            exec_log = exec_log.model_copy(update={
                "finished_at": datetime.now(timezone.utc),
                "status": status,
                "records_in": records_in,
                "records_ok": ok,
                "records_failed": failed,
                "duration_ms": duration_ms,
            })
            self.repo.finish_run(exec_log)
            log.info(
                f"[{self.name}] Fim: status={status} in={records_in} "
                f"ok={ok} fail={failed} dur={duration_ms}ms"
            )
            return exec_log

        except Exception as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            log.error(f"[{self.name}] Falha fatal: {err}")
            exec_log = exec_log.model_copy(update={
                "finished_at": datetime.now(timezone.utc),
                "status": "FAILED",
                "records_in": records_in,
                "records_ok": ok,
                "records_failed": records_in - ok,
                "duration_ms": duration_ms,
                "error_message": err[:2000],
            })
            try:
                self.repo.finish_run(exec_log)
            except Exception:
                log.exception("Falha persistindo execution_log de falha")
            return exec_log

    # ------------------ pipeline interno -----------------------------------

    def _process_record(self, raw: AssetReadingRaw, log: Any) -> None:
        raw_id = self.repo.insert_raw(raw)
        if raw_id is None:
            log.debug(f"Registro duplicado ignorado: {raw.source}/{raw.source_id}")
            return

        normalized = normalize_payload(raw.payload)
        scored = validate_and_score(normalized)

        asset_id = self.repo.get_asset_id_by_tag(raw.asset_tag)

        clean = AssetReadingClean(
            raw_id=raw_id,
            asset_id=asset_id,
            asset_tag=raw.asset_tag,
            measured_at=scored["measured_at"] or raw.received_at,
            temperature_c=scored.get("temperature_c"),
            vibration_mm_s=scored.get("vibration_mm_s"),
            current_a=scored.get("current_a"),
            voltage_v=scored.get("voltage_v"),
            rpm=scored.get("rpm"),
            power_kw=scored.get("power_kw"),
            quality_score=scored["quality_score"],
            flags=scored.get("flags", {}),
        )
        self.repo.insert_clean(clean)

    # ------------------ contrato pra subclasses ----------------------------

    @abstractmethod
    def extract(self) -> Iterable[Any]:
        """Yields registros brutos (formato livre — dict, linha CSV, JSON, etc)."""

    @abstractmethod
    def parse(self, record: Any, run_id) -> AssetReadingRaw:
        """Converte um registro bruto pra AssetReadingRaw (validado)."""
