"""Repository pattern: encapsula TODA a interação SQL com o Postgres.

Decisões:
  - UPSERT idempotente em assets (evita duplicar cadastro)
  - INSERT ON CONFLICT DO NOTHING em readings_raw (idempotência por (source, source_id))
  - SCD type 2: UPDATE assets_history fechando valid_to da versão anterior + INSERT da nova
  - Tudo via context manager → conexão auto-close
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from src.db.connection import get_connection
from src.models.asset import (
    Asset,
    AssetReadingClean,
    AssetReadingRaw,
    ExecutionLog,
)


class Repository:
    """Camada de acesso a dados. Cada método abre/fecha sua conexão."""

    # ------------------------- ASSETS (CADASTRO) ---------------------------

    def upsert_asset(self, asset: Asset, changed_by: str, reason: str = "") -> int:
        """UPSERT no cadastro + registro SCD type 2 quando há mudança real.

        Retorna o ID do asset.
        """
        snapshot = asset.model_dump(mode="json")

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, manufacturer, model, rated_power_kw, rated_voltage_v, "
                "rated_current_a, rated_rpm, location, installation_date, status "
                "FROM assets WHERE tag = %s",
                (asset.tag,),
            )
            existing = cur.fetchone()

            if existing is None:
                cur.execute(
                    """
                    INSERT INTO assets (
                        tag, name, manufacturer, model,
                        rated_power_kw, rated_voltage_v, rated_current_a, rated_rpm,
                        location, installation_date, status
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        asset.tag, asset.name, asset.manufacturer, asset.model,
                        asset.rated_power_kw, asset.rated_voltage_v,
                        asset.rated_current_a, asset.rated_rpm,
                        asset.location, asset.installation_date, asset.status,
                    ),
                )
                asset_id = cur.fetchone()[0]
                self._insert_history(cur, asset_id, asset.tag, snapshot, changed_by, reason or "INSERT")
                conn.commit()
                return asset_id

            asset_id = existing[0]
            current = {
                "manufacturer": existing[1],
                "model": existing[2],
                "rated_power_kw": float(existing[3]) if existing[3] is not None else None,
                "rated_voltage_v": float(existing[4]) if existing[4] is not None else None,
                "rated_current_a": float(existing[5]) if existing[5] is not None else None,
                "rated_rpm": existing[6],
                "location": existing[7],
                "installation_date": existing[8].isoformat() if existing[8] else None,
                "status": existing[9],
            }
            incoming = {
                "manufacturer": asset.manufacturer,
                "model": asset.model,
                "rated_power_kw": asset.rated_power_kw,
                "rated_voltage_v": asset.rated_voltage_v,
                "rated_current_a": asset.rated_current_a,
                "rated_rpm": asset.rated_rpm,
                "location": asset.location,
                "installation_date": asset.installation_date.isoformat() if asset.installation_date else None,
                "status": asset.status,
            }

            if current != incoming:
                cur.execute(
                    """
                    UPDATE assets SET
                        name = %s, manufacturer = %s, model = %s,
                        rated_power_kw = %s, rated_voltage_v = %s,
                        rated_current_a = %s, rated_rpm = %s,
                        location = %s, installation_date = %s, status = %s
                    WHERE id = %s
                    """,
                    (
                        asset.name, asset.manufacturer, asset.model,
                        asset.rated_power_kw, asset.rated_voltage_v,
                        asset.rated_current_a, asset.rated_rpm,
                        asset.location, asset.installation_date, asset.status,
                        asset_id,
                    ),
                )
                self._insert_history(cur, asset_id, asset.tag, snapshot, changed_by, reason or "UPDATE")

            conn.commit()
            return asset_id

    def _insert_history(
        self,
        cur: psycopg.Cursor,
        asset_id: int,
        tag: str,
        snapshot: dict[str, Any],
        changed_by: str,
        reason: str,
    ) -> None:
        """Fecha versão anterior (valid_to=NOW) e abre nova versão."""
        cur.execute(
            "UPDATE assets_history SET valid_to = NOW() "
            "WHERE asset_id = %s AND valid_to IS NULL",
            (asset_id,),
        )
        cur.execute(
            "INSERT INTO assets_history (asset_id, tag, snapshot, changed_by, change_reason) "
            "VALUES (%s, %s, %s, %s, %s)",
            (asset_id, tag, Jsonb(snapshot), changed_by, reason),
        )

    def get_asset_id_by_tag(self, tag: str) -> int | None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM assets WHERE tag = %s", (tag,))
            row = cur.fetchone()
            return row[0] if row else None

    # ------------------------- READINGS (BRONZE/SILVER) --------------------

    def insert_raw(self, reading: AssetReadingRaw) -> int | None:
        """INSERT idempotente em readings_raw. Retorna id (ou None se duplicado)."""
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO readings_raw
                    (asset_tag, source, source_id, payload, received_at, run_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, source_id) DO NOTHING
                RETURNING id
                """,
                (
                    reading.asset_tag,
                    reading.source,
                    reading.source_id,
                    Jsonb(reading.payload),
                    reading.received_at,
                    str(reading.run_id),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None

    def insert_clean(self, reading: AssetReadingClean) -> int | None:
        """INSERT idempotente em readings_clean (UNIQUE por raw_id)."""
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO readings_clean (
                    raw_id, asset_id, asset_tag, measured_at,
                    temperature_c, vibration_mm_s, current_a, voltage_v,
                    rpm, power_kw, quality_score, flags
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (raw_id) DO NOTHING
                RETURNING id
                """,
                (
                    reading.raw_id, reading.asset_id, reading.asset_tag,
                    reading.measured_at,
                    reading.temperature_c, reading.vibration_mm_s,
                    reading.current_a, reading.voltage_v,
                    reading.rpm, reading.power_kw,
                    reading.quality_score, Jsonb(reading.flags),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None

    # ------------------------- EXECUTION LOGS ------------------------------

    def start_run(self, log: ExecutionLog) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_logs
                    (run_id, bot_name, started_at, status, metadata)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    str(log.run_id), log.bot_name, log.started_at,
                    log.status, Jsonb(log.metadata),
                ),
            )
            conn.commit()

    def finish_run(self, log: ExecutionLog) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE execution_logs SET
                    finished_at = %s,
                    status = %s,
                    records_in = %s,
                    records_ok = %s,
                    records_failed = %s,
                    duration_ms = %s,
                    error_message = %s,
                    metadata = metadata || %s
                WHERE run_id = %s
                """,
                (
                    log.finished_at, log.status,
                    log.records_in, log.records_ok, log.records_failed,
                    log.duration_ms, log.error_message,
                    Jsonb(log.metadata),
                    str(log.run_id),
                ),
            )
            conn.commit()

    # ------------------------- DASHBOARD QUERIES ---------------------------

    def list_assets_with_last_reading(self) -> list[dict[str, Any]]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM v_assets_current ORDER BY tag")
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def recent_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT bot_name, started_at, finished_at, status, "
                "records_in, records_ok, records_failed, duration_ms, error_message "
                "FROM execution_logs ORDER BY started_at DESC LIMIT %s",
                (limit,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def readings_history(self, asset_tag: str, hours: int = 24) -> list[dict[str, Any]]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT measured_at, temperature_c, vibration_mm_s,
                       current_a, voltage_v, rpm, power_kw, quality_score
                FROM readings_clean
                WHERE asset_tag = %s
                  AND measured_at >= NOW() - (%s || ' hours')::interval
                ORDER BY measured_at ASC
                """,
                (asset_tag, str(hours)),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
