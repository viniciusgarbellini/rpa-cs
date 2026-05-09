"""Gera planilha de exemplo pro ManualBot.

Uso (dentro do container ou venv):
    python -m src.tools.gen_manual_xlsx

Cria um .xlsx em data/manual/ simulando uma planilha de ronda de manutenção
preenchida por operadores em campo.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openpyxl

from src.config import settings


HEADER = [
    "asset_tag", "timestamp", "temperature", "temperature_unit",
    "vibration", "vibration_unit", "current", "current_unit",
    "voltage", "voltage_unit", "rpm", "operator",
]

ASSETS = ["MTR-001", "MTR-002", "MTR-003", "MTR-004"]


def main() -> None:
    settings.manual_folder.mkdir(parents=True, exist_ok=True)
    out = settings.manual_folder / "ronda_manutencao.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ronda Semanal"
    ws.append(HEADER)

    # Gera 12 leituras manuais (ronda de 3 dias × 4 ativos)
    base = datetime.now(timezone.utc) - timedelta(days=3)
    for i in range(12):
        when = base + timedelta(hours=i * 6)
        tag = ASSETS[i % len(ASSETS)]
        ws.append([
            tag,
            when.isoformat(),
            round(random.uniform(40, 90), 1),
            "°C",
            round(random.uniform(1.0, 4.5), 2),
            "mm/s",
            round(random.uniform(30, 280), 1),
            "A",
            round(random.uniform(380, 460), 1),
            "V",
            int(random.uniform(1700, 3580)),
            random.choice(["Silva", "Almeida", "Rocha"]),
        ])

    wb.save(out)
    print(f"Planilha gerada: {out}")


if __name__ == "__main__":
    main()
