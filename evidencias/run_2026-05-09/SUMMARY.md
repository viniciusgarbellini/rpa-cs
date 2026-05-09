# Evidências de execução — 2026-05-09

Snapshot de uma execução completa do pipeline RPA, capturada após múltiplos ciclos
dos 4 bots rodando via APScheduler. Atende aos itens da rubrica:

- ✅ **Logs ou evidências da execução das automações** → `rpa.log`, `ultimas_execucoes.txt`, `resumo_por_bot.txt`
- ✅ **Base de dados inicial populada com histórico de ativos** → `rpa_assets_dump.sql`, `assets_history_sample.txt`

---

## Estado do banco no momento da captura

| Tabela           | Linhas |
|------------------|-------:|
| `readings_raw`   |  2.671 |
| `readings_clean` |  2.671 |
| `assets_history` |     24 |
| `execution_logs` |    117 |

(detalhe completo em `snapshot_counts.txt`)

## Resumo por bot

| Bot          | Execuções | Registros OK | Falhas | Duração média (ms) |
|--------------|----------:|-------------:|-------:|-------------------:|
| `api_bot`    |        21 |          659 |      0 |              1.594 |
| `file_bot`   |        31 |           18 |      0 |                 40 |
| `manual_bot` |        14 |            0 |      0 |                 27 |
| `sensor_bot` |        53 |        2.986 |      0 |              2.503 |

**Taxa de sucesso: 100%** (zero falhas em 119 execuções).

(detalhe em `resumo_por_bot.txt`)

---

## Conteúdo da pasta

| Arquivo                       | O que é |
|-------------------------------|---------|
| `rpa.log`                     | Log JSON estruturado (Loguru) — todas as execuções dos bots, com `run_id` por ciclo |
| `rpa_assets_dump.sql`         | Dump completo do PostgreSQL (`pg_dump`): schema + dados — restaurável com `psql` |
| `snapshot_counts.txt`         | Contagem de linhas em cada tabela principal |
| `ultimas_execucoes.txt`       | Últimas 20 execuções dos bots (status, duração, registros processados) |
| `resumo_por_bot.txt`          | Agregação por bot (execuções, OK, falhas, latência média) |
| `assets_history_sample.txt`   | Amostra do histórico SCD type 2 — mostra versões consecutivas dos motores MTR-001 a MTR-004 |
| `readings_clean_sample.txt`   | Amostra das últimas 20 leituras já normalizadas em SI (silver) |

---

## Como restaurar o banco a partir do dump

```bash
docker compose up -d postgres
docker exec -i rpa_postgres psql -U rpa -d rpa_assets < evidencias/run_2026-05-09/rpa_assets_dump.sql
```

Depois é só `docker compose up -d` para subir o resto da stack — o orquestrador
e o dashboard já encontrarão a base populada.

---

## Como esses dados foram coletados

```bash
# 1) Subir a stack
docker compose up --build -d

# 2) Aguardar os bots rodarem alguns ciclos (sensor a cada 1min, file a cada 2min, etc.)

# 3) Snapshot dos contadores
docker exec rpa_postgres psql -U rpa -d rpa_assets -c "SELECT ... FROM execution_logs ..."

# 4) pg_dump completo
docker exec rpa_postgres pg_dump -U rpa -d rpa_assets --no-owner --no-privileges \
  > evidencias/run_2026-05-09/rpa_assets_dump.sql

# 5) Cópia do log atual
cp logs/rpa.log evidencias/run_2026-05-09/rpa.log
```
