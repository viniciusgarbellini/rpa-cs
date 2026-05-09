# Decisões técnicas (ADRs)

> Cada ADR (Architecture Decision Record) registra uma decisão importante,
> as alternativas consideradas e a razão da escolha.
> O professor pediu explicitamente "justificativas das decisões — muito importante".

---

## ADR-001 — Linguagem: Python 3.12

**Contexto.** O escopo é RPA + ETL + integração com REST + leitura de CSV/XLSX.

**Alternativas consideradas:**
- **Java/Spring Batch** — robusto pra ETL, mas overkill pra MVP e curva alta.
- **Node.js** — bom pra integração, ecossistema fraco em RPA/ciência de dados.
- **C#/.NET** — comum em RPA corporativo (UiPath), mas exige Windows-host.
- **Robocorp/RPAFramework** — RPA "canônico", mas restritivo pra orquestração customizada.

**Decisão.** Python 3.12 com bibliotecas padronizadas (Pydantic, FastAPI, pandas).

**Por quê:**
- Ecossistema RPA + Data Engineering + ML maduro (a próxima sprint é Digital Twin/ML).
- Bibliotecas idiomáticas: APScheduler, Loguru, openpyxl, requests, psycopg.
- Testabilidade com pytest é trivial.
- Mesmo time pode evoluir para Prefect/Airflow sem trocar a linguagem.

**Consequência.** Compromete-se com runtime CPython e GIL — mas o gargalo aqui
é I/O (HTTP + Postgres), não CPU, então o GIL é irrelevante.

---

## ADR-002 — Banco: PostgreSQL 16 (relacional + JSONB)

**Contexto.** O enunciado oferece três opções: relacional, NoSQL, ou arquivos
estruturados. Pede explicitamente justificativa técnica.

**Alternativas consideradas:**

| Opção                  | Prós                                        | Contras |
|------------------------|---------------------------------------------|---------|
| **MongoDB**            | flexibilidade de schema, fácil JSON         | sem ACID multi-doc histórico; integridade referencial fraca |
| **InfluxDB/TimescaleDB**| séries temporais por design                | pra MVP é overkill; cadastro de ativos não é série temporal |
| **Parquet em pasta**   | barato, ideal pra Data Lake                 | sem queries online, sem joins, péssimo pra dashboard |
| **PostgreSQL**         | ACID, SQL, JSONB, view, trigger, ecossistema| INSERTs unitários requerem mais cuidado em escala |

**Decisão.** PostgreSQL 16, com colunas tipadas para o cadastro/leituras
canônicas e `JSONB` para `payload` raw + `flags` + `metadata`.

**Por quê:**
1. **Cadastro de motores tem schema previsível** (tag, fabricante, potência…)
   → relacional é a representação natural.
2. **ACID** garante rastreabilidade — requisito explícito.
3. **JSONB** dá flexibilidade onde precisa (raw payloads heterogêneos das fontes).
4. **SCD type 2** (histórico) é trivial em SQL; em Mongo seria reinventar.
5. Postgres é **infraestrutura comoditizada** — qualquer cloud, fácil backup.
6. Em escala futura, **TimescaleDB é uma extensão Postgres** — adicionar não é
   migração, é `CREATE EXTENSION` (preserva o investimento).

**Consequência.** Inserts unitários em alto volume serão um gargalo eventual.
Mitigação prevista: trocar por `COPY` em batch quando volume cruzar ~1M leituras/dia.

---

## ADR-003 — Orquestração: APScheduler in-process

**Alternativas:**
- **cron do sistema** — simples, mas exige container alpine cron, log fragmentado.
- **Airflow / Prefect** — overkill pra 4 jobs.
- **Celery beat** — adiciona Redis, complexidade extra.

**Decisão.** APScheduler in-process com `BackgroundScheduler`.

**Por quê:**
- 1 processo, 1 container, scheduler convive com os bots na mesma memória.
- Cron expressions familiares (`*/2 * * * *`).
- `max_instances=1` previne sobreposição se um job atrasar.
- `coalesce=True` agrupa execuções perdidas — sem flood pós-downtime.
- Migração futura pra Celery/Prefect mantém o `BaseBot` intacto.

---

## ADR-004 — Idempotência via UNIQUE(source, source_id)

**Problema.** Bots RPA são propensos a re-executar a mesma janela (replay,
retry, double-trigger). Sem idempotência, o histórico inflaciona.

**Decisão.** Toda fonte gera um `source_id` estável e único:

| Bot         | `source_id`                                  |
|-------------|----------------------------------------------|
| file_bot    | `<arquivo>:L<linha>`                          |
| api_bot     | `<tag>:<id_da_API>`                           |
| sensor_bot  | `sensor:<id_da_mensagem>`                     |
| manual_bot  | `<arquivo>:<sheet>:L<linha>`                  |

`UNIQUE(source, source_id)` na `readings_raw` + `INSERT ON CONFLICT DO NOTHING`
torna a operação **idempotente** sem locking caro.

---

## ADR-005 — Validação na fronteira via Pydantic

**Princípio.** "Parse, don't validate" (Alexis King).
Todo dado externo é convertido em **objeto tipado** antes de tocar a lógica.

**Decisão.** Usar Pydantic v2 com:
- `Asset.tag` exige regex `^[A-Z0-9\-_]+$`
- `rated_power_kw`, `temperature_c`, etc com `ge`/`le` absurdos (10_000 kW, 300°C)
- `source` Literal `["file","legacy_api","sensor_iot","manual"]`

**Resultado.** Erros de tipo/range são capturados antes do SQL, viram log
estruturado, incrementam `records_failed`. O banco nunca recebe lixo.

---

## ADR-006 — Logs estruturados (Loguru JSON) com run_id

**Decisão.**
- Stdout: legível pro humano em desenvolvimento.
- Arquivo `logs/rpa.log`: **sempre JSON serialize=True**, rotacionado a 10MB.
- Toda mensagem inclui `bot` e `run_id` via `logger.bind()`.

**Por quê.** O run_id casa com `execution_logs.run_id` e com `readings_raw.run_id`,
permitindo **rastreamento end-to-end**: a partir de uma leitura no banco, achar
exatamente o ciclo do bot que a produziu, e os logs daquela execução.

---

## ADR-007 — Containers separados por responsabilidade

**Decisão.** 5 containers (Postgres, legacy-api, sensor-sim, orchestrator, dashboard)
em vez de monolito.

**Por quê.**
- Cada serviço escala independentemente.
- Mock APIs simulam um ambiente real distribuído.
- O orquestrador pode ser substituído (Celery, Prefect…) sem mexer no resto.
- Falha de container não derruba os outros.

**Trade-off.** Build mais lento na primeira vez (~2 min). Aceitável.

---

## ADR-008 — Mock services em FastAPI (em vez de MQTT broker real)

**Contexto.** O enunciado pede "sensores IoT" como uma das fontes. O caminho
natural seria Mosquitto (MQTT).

**Decisão.** Substituir MQTT por um **simulador HTTP** que entrega a mesma semântica
(produtor → buffer → consumidor → ack).

**Por quê.**
- O foco da sprint é **RPA**, não infra IoT — não vale o custo cognitivo de MQTT
  para um MVP demonstrativo.
- A interface `extract()` do `SensorBot` é **isolada**: trocar HTTP por
  `paho-mqtt` é uma mudança local de ~30 linhas. A arquitetura está preparada.
- Mosquitto adicionaria mais um container só pra demo.

→ Documentado como caminho de evolução para a próxima sprint.

---

## ADR-009 — Manter dados ruins com score baixo (vs descartar)

**Decisão.** Leituras com unidade desconhecida, valor fora de faixa ou
timestamp suspeito **vão pro banco mesmo assim**, com `flags` populadas e
`quality_score < 1`.

**Por quê.**
- Detecção de **drift de sensor** depende de ver os valores ruins ao longo
  do tempo, não só os bons.
- O Digital Twin (próxima sprint) pode optar por filtrar `quality_score >= 0.7`
  no consumo, sem perder visibilidade de longo prazo.
- "Garbage in, score out" — o score é a forma de distinguir, não o silêncio.

---

## ADR-010 — Visualização: Streamlit (em vez de Grafana)

**Alternativas.** Grafana (excelente pra séries temporais) ou Metabase.

**Decisão.** Streamlit + Plotly.

**Por quê.**
- Implementação em ~80 linhas Python (não YAML/JSON de Grafana).
- Reusa direto o `Repository` — sem precisar de um data source adicional.
- Pra escala, adicionar Grafana por cima é trivial (mesma origem de dados).

---

## ADR-011 — Schema bronze/silver (não gold ainda)

**Decisão.** Implementar duas camadas (`readings_raw`, `readings_clean`) e
deixar a camada **gold** (agregada/business) para a próxima sprint.

**Por quê.** A camada gold depende das **regras analíticas do Digital Twin**,
que ainda não foram definidas. Construir agregações agora seria adivinhar.
A view `v_assets_current` é o único lampejo de gold — utilitária pro dashboard.
