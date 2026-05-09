"""Entrypoint da automação RPA.

Modos:
  python -m src.main init       → cria schema + popula cadastro inicial
  python -m src.main run        → inicia orquestrador (loop principal)
  python -m src.main bot <nome> → executa 1 bot uma vez (ad-hoc)
"""

from __future__ import annotations

import sys

from src.bots.api_bot import ApiBot
from src.bots.file_bot import FileBot
from src.bots.manual_bot import ManualBot
from src.bots.sensor_bot import SensorBot
from src.db.connection import init_db
from src.db.repository import Repository
from src.logger import get_logger, setup_logger
from src.models.asset import Asset
from src.orchestrator import run_forever


SEED_ASSETS = [
    Asset(
        tag="MTR-001", name="Motor Bomba Centrífuga 01",
        manufacturer="WEG", model="W22 IR3",
        rated_power_kw=75.0, rated_voltage_v=440.0,
        rated_current_a=130.0, rated_rpm=3550,
        location="Linha 1 - Bombeamento",
    ),
    Asset(
        tag="MTR-002", name="Motor Compressor Parafuso 02",
        manufacturer="Atlas Copco", model="GA-160",
        rated_power_kw=160.0, rated_voltage_v=440.0,
        rated_current_a=280.0, rated_rpm=1780,
        location="Casa de Compressores",
    ),
    Asset(
        tag="MTR-003", name="Motor Esteira Transportadora 03",
        manufacturer="Siemens", model="SIMOTICS GP",
        rated_power_kw=22.0, rated_voltage_v=380.0,
        rated_current_a=42.0, rated_rpm=1750,
        location="Linha 2 - Conveyor",
        status="MAINTENANCE",
    ),
    Asset(
        tag="MTR-004", name="Motor Ventilador Industrial 04",
        manufacturer="WEG", model="W22 IR4",
        rated_power_kw=45.0, rated_voltage_v=440.0,
        rated_current_a=80.0, rated_rpm=1185,
        location="Casa de Máquinas - Exaustão",
    ),
]


BOTS = {
    "file": FileBot,
    "api": ApiBot,
    "sensor": SensorBot,
    "manual": ManualBot,
}


def cmd_init() -> None:
    log = get_logger("init")
    log.info("Inicializando schema do banco…")
    init_db()
    log.info("Populando cadastro de ativos (seed)…")
    repo = Repository()
    for asset in SEED_ASSETS:
        repo.upsert_asset(asset, changed_by="init", reason="seed")
    log.info(f"{len(SEED_ASSETS)} ativos carregados.")


def cmd_run() -> None:
    log = get_logger("main")
    log.info("Garantindo schema antes do start…")
    init_db()
    repo = Repository()
    for asset in SEED_ASSETS:
        repo.upsert_asset(asset, changed_by="bootstrap", reason="ensure_seed")
    run_forever()


def cmd_bot(name: str) -> None:
    log = get_logger("main")
    cls = BOTS.get(name)
    if cls is None:
        log.error(f"Bot desconhecido: {name}. Disponíveis: {list(BOTS)}")
        sys.exit(2)
    log.info(f"Execução ad-hoc: {name}")
    cls().run()


def main() -> None:
    setup_logger()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    cmd, *rest = args
    if cmd == "init":
        cmd_init()
    elif cmd == "run":
        cmd_run()
    elif cmd == "bot" and rest:
        cmd_bot(rest[0])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
