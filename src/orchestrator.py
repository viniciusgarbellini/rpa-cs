"""Orquestrador APScheduler — agenda os 4 bots e mantém o processo vivo.

Atende aos requisitos:
  - "rotina automatizada de atualização" (cron por bot)
  - "execução sem intervenção manual"
  - "logs automatizados que permitam rastreabilidade"

Cada bot roda no seu próprio horário (configurável por env). Em caso de
falha de uma execução, o scheduler mantém as próximas agendas — falha
isolada não derruba o sistema (atende "robustez básica").
"""

from __future__ import annotations

import signal
import sys
import time
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bots.api_bot import ApiBot
from src.bots.file_bot import FileBot
from src.bots.manual_bot import ManualBot
from src.bots.sensor_bot import SensorBot
from src.config import settings
from src.logger import get_logger


def _safe_run(bot: Any) -> None:
    """Wrapper: nunca propaga exceção pro APScheduler (mantém schedule vivo)."""
    log = get_logger(bot.name)
    try:
        bot.run()
    except Exception as e:
        log.exception(f"Erro inesperado em {bot.name}: {e}")


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")

    bots = {
        FileBot():    settings.schedule_file_bot,
        ApiBot():     settings.schedule_api_bot,
        SensorBot():  settings.schedule_sensor_bot,
        ManualBot():  settings.schedule_manual_bot,
    }

    for bot, cron in bots.items():
        sched.add_job(
            _safe_run,
            trigger=CronTrigger.from_crontab(cron, timezone="UTC"),
            args=[bot],
            id=bot.name,
            name=bot.name,
            max_instances=1,           # nunca duas execuções do mesmo bot em paralelo
            coalesce=True,             # se atrasou, agrupa em 1
            misfire_grace_time=60,
        )

    return sched


def run_forever() -> None:
    log = get_logger("orchestrator")

    sched = build_scheduler()

    # Disparo inicial: roda todos os bots 1x na subida pra popular dados
    log.info("Disparando warm-up (1 execução de cada bot)…")
    for job in sched.get_jobs():
        bot = job.args[0]
        _safe_run(bot)

    sched.start()
    log.info("Orquestrador iniciado. Schedules ativos:")
    for job in sched.get_jobs():
        log.info(f"  • {job.name} → {job.trigger}")

    # Graceful shutdown
    stop = {"flag": False}

    def _handler(signum, _frame):  # noqa: ANN001
        log.info(f"Recebido sinal {signum}, encerrando…")
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)

    try:
        while not stop["flag"]:
            time.sleep(1)
    finally:
        sched.shutdown(wait=True)
        log.info("Orquestrador finalizado.")
