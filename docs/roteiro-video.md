# Roteiro do vídeo de demonstração (3-5 min)

> Esse roteiro garante que **toda evidência de avaliação** apareça em vídeo.

---

## Estrutura sugerida (4 minutos total)

### 0:00 — 0:30 · Abertura (mostre o problema)
- Mostre o README aberto.
- Fale: "esta é a sprint inicial do projeto de monitoramento e manutenção
  preditiva de motores industriais. Aqui as automações coletam dados de
  4 fontes diferentes, normalizam unidades, persistem com auditoria, e
  alimentam a base do futuro Digital Twin."
- Mostre o diagrama Mermaid no `docs/arquitetura.md`.

### 0:30 — 0:50 · Sobe a stack
- Em um terminal: `docker compose up --build`
- Mostre os 5 containers ficando saudáveis.
- Explique: "Postgres, mock API legado, simulador de sensor IoT,
  orquestrador RPA com 4 bots, e o dashboard."

### 0:50 — 1:30 · Dashboard funcional (evidência visual)
- Abra http://localhost:8501
- Mostre os 4 cards de motor com leituras chegando.
- Selecione um motor → gráficos de temperatura/vibração/potência/qualidade.
- Mostre a tabela de **execuções recentes** (auditoria RPA): bot_name,
  records_in/ok/failed, status, duração.
- "Repare que o sensor_bot dispara a cada minuto, o file_bot a cada 2 min, etc."

### 1:30 — 2:15 · Demonstre coleta de arquivo (FileBot)
- Em outro terminal: `cp data/samples/readings_pcm_2026-05-08.csv data/drop/`
- Em ~2 min (ou force `docker exec rpa_orchestrator python -m src.main bot file`):
  - Volta no dashboard → nova execução `file_bot SUCCESS records_in=7 ok=7`
  - Mostre `data/archive/` — arquivo movido com sufixo de timestamp
- Mostre `data/samples/readings_termografia_2026-05-09.csv` que tem temperatura
  em **°F** → coloque no drop, aponte que após coleta o dashboard mostra °C.
  "Olha a normalização funcionando: a fonte mandou 140°F, o banco gravou 60°C."

### 2:15 — 2:50 · Banco de dados estruturado
```bash
docker exec -it rpa_postgres psql -U rpa -d rpa_assets
```

```sql
-- Cadastro
SELECT tag, name, status, rated_power_kw FROM assets;

-- Histórico de mudanças
SELECT tag, valid_from, valid_to, changed_by, change_reason
FROM assets_history ORDER BY valid_from DESC LIMIT 5;

-- Leituras normalizadas
SELECT asset_tag, measured_at, temperature_c, vibration_mm_s,
       power_kw, quality_score, flags
FROM readings_clean ORDER BY measured_at DESC LIMIT 10;

-- Auditoria RPA
SELECT bot_name, status, records_in, records_ok, records_failed,
       duration_ms FROM execution_logs ORDER BY started_at DESC LIMIT 10;
```

Comente: "ACID, idempotência via UNIQUE, histórico SCD type 2, rastreabilidade
completa via run_id."

### 2:50 — 3:20 · Logs estruturados
```bash
docker compose logs --tail=50 rpa-orchestrator
```
"Logs em JSON com run_id por execução, rotacionados em arquivo."
```bash
tail -1 logs/rpa.log | python -m json.tool
```

### 3:20 — 3:50 · Robustez
- Pare o `legacy-api`: `docker compose stop legacy-api`
- Espere 1 ciclo do api_bot → mostre execution_log com `status=FAILED` e
  `error_message`.
- Mostre que **os outros bots seguem rodando**.
- Suba de novo: `docker compose start legacy-api` → próximo ciclo SUCCESS.

### 3:50 — 4:00 · Fechamento
- Mostre os testes: `docker exec rpa_orchestrator pytest`
- Aponte o `docs/decisoes-tecnicas.md` (ADRs).
- "Próxima sprint: análise inteligente sobre `readings_clean`."

---

## Checklist de evidências (todas devem estar no vídeo)

- [ ] 4 fontes coletando (`v_assets_current` populada, todos os 4 ativos)
- [ ] Dashboard com gráficos renderizados
- [ ] CSV processado e arquivado (file_bot)
- [ ] Conversão de unidade °F→°C demonstrada (termografia.csv)
- [ ] `execution_logs` com várias execuções de bots diferentes
- [ ] Histórico em `assets_history`
- [ ] Log estruturado JSON
- [ ] Falha isolada (legacy-api derrubada → status=FAILED, outros bots OK)
- [ ] `pytest` passando
