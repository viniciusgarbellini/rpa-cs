-- =============================================================================
-- Schema: RPA CS — Coleta, Registro e Atualização de Dados de Ativos (Motores)
-- =============================================================================
-- Justificativa técnica:
--   Banco RELACIONAL (PostgreSQL) escolhido porque:
--     1. Cadastro de ativos tem schema rígido e bem definido (motores industriais
--        têm campos previsíveis: tag, fabricante, potência nominal, etc).
--     2. Garantias ACID são críticas pra rastreabilidade (req. funcional).
--     3. SCD type 2 + JSONB cobre histórico de mudanças sem perder estrutura.
--     4. Relacionamentos asset ↔ readings ↔ logs são naturalmente relacionais.
--     5. Postgres oferece JSONB pra flexibilidade onde precisa (raw payloads).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Tabela: assets — Cadastro mestre dos motores elétricos
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assets (
    id              SERIAL          PRIMARY KEY,
    tag             VARCHAR(50)     UNIQUE NOT NULL,
    name            VARCHAR(200)    NOT NULL,
    manufacturer    VARCHAR(100),
    model           VARCHAR(100),
    rated_power_kw  NUMERIC(10,2),
    rated_voltage_v NUMERIC(10,2),
    rated_current_a NUMERIC(10,2),
    rated_rpm       INTEGER,
    location        VARCHAR(200),
    installation_date DATE,
    status          VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','INACTIVE','MAINTENANCE')),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);

-- -----------------------------------------------------------------------------
-- Tabela: assets_history — SCD type 2 (histórico de mudanças no cadastro)
-- -----------------------------------------------------------------------------
-- Toda alteração no cadastro gera uma linha aqui. valid_to NULL = versão atual.
-- Atende: "histórico das atualizações realizadas" (req. funcional).
CREATE TABLE IF NOT EXISTS assets_history (
    id              BIGSERIAL       PRIMARY KEY,
    asset_id        INTEGER         REFERENCES assets(id) ON DELETE CASCADE,
    tag             VARCHAR(50)     NOT NULL,
    snapshot        JSONB           NOT NULL,
    valid_from      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    valid_to        TIMESTAMPTZ,
    changed_by      VARCHAR(100)    NOT NULL,
    change_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_assets_history_tag    ON assets_history(tag);
CREATE INDEX IF NOT EXISTS idx_assets_history_active ON assets_history(asset_id) WHERE valid_to IS NULL;

-- -----------------------------------------------------------------------------
-- Tabela: readings_raw — Leituras brutas (camada bronze, imutável)
-- -----------------------------------------------------------------------------
-- Persiste o payload original sem transformação.
-- UNIQUE (source, source_id) garante IDEMPOTÊNCIA: mesmo registro reprocessado
-- não duplica. Atende: "validação e integridade" + "rastreabilidade".
CREATE TABLE IF NOT EXISTS readings_raw (
    id              BIGSERIAL       PRIMARY KEY,
    asset_tag       VARCHAR(50)     NOT NULL,
    source          VARCHAR(50)     NOT NULL
                    CHECK (source IN ('file','legacy_api','sensor_iot','manual')),
    source_id       VARCHAR(200)    NOT NULL,
    payload         JSONB           NOT NULL,
    received_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    run_id          UUID            NOT NULL,
    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_tag_received ON readings_raw(asset_tag, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_run          ON readings_raw(run_id);

-- -----------------------------------------------------------------------------
-- Tabela: readings_clean — Leituras normalizadas (camada silver, SI)
-- -----------------------------------------------------------------------------
-- Dados convertidos pra unidades SI (°C, V, A, kW, mm/s, rpm).
-- flags armazena anomalias detectadas (out_of_range, missing, suspicious).
CREATE TABLE IF NOT EXISTS readings_clean (
    id              BIGSERIAL       PRIMARY KEY,
    raw_id          BIGINT          NOT NULL REFERENCES readings_raw(id) ON DELETE CASCADE,
    asset_id        INTEGER         REFERENCES assets(id),
    asset_tag       VARCHAR(50)     NOT NULL,
    measured_at     TIMESTAMPTZ     NOT NULL,
    temperature_c   NUMERIC(8,2),
    vibration_mm_s  NUMERIC(8,2),
    current_a       NUMERIC(8,2),
    voltage_v       NUMERIC(8,2),
    rpm             INTEGER,
    power_kw        NUMERIC(10,2),
    quality_score   NUMERIC(3,2)    CHECK (quality_score BETWEEN 0 AND 1),
    flags           JSONB           DEFAULT '{}'::jsonb,
    processed_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (raw_id)
);

CREATE INDEX IF NOT EXISTS idx_clean_asset_time ON readings_clean(asset_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_clean_tag_time   ON readings_clean(asset_tag, measured_at DESC);

-- -----------------------------------------------------------------------------
-- Tabela: execution_logs — Logs de execução das automações RPA
-- -----------------------------------------------------------------------------
-- Cada execução de bot gera 1 linha. Permite auditoria completa:
-- quando rodou, quanto demorou, quantos registros entraram/saíram, erros.
CREATE TABLE IF NOT EXISTS execution_logs (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            UNIQUE NOT NULL,
    bot_name        VARCHAR(50)     NOT NULL,
    started_at      TIMESTAMPTZ     NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20)     NOT NULL
                    CHECK (status IN ('RUNNING','SUCCESS','FAILED','PARTIAL')),
    records_in      INTEGER         NOT NULL DEFAULT 0,
    records_ok      INTEGER         NOT NULL DEFAULT 0,
    records_failed  INTEGER         NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    error_message   TEXT,
    metadata        JSONB           DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_exec_logs_bot_time ON execution_logs(bot_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_exec_logs_status   ON execution_logs(status);

-- -----------------------------------------------------------------------------
-- View: v_assets_current — última versão ativa do cadastro com últimas leituras
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_assets_current AS
SELECT
    a.id,
    a.tag,
    a.name,
    a.manufacturer,
    a.model,
    a.rated_power_kw,
    a.status,
    lr.measured_at        AS last_reading_at,
    lr.temperature_c      AS last_temperature_c,
    lr.vibration_mm_s     AS last_vibration_mm_s,
    lr.current_a          AS last_current_a,
    lr.power_kw           AS last_power_kw
FROM assets a
LEFT JOIN LATERAL (
    SELECT *
    FROM readings_clean rc
    WHERE rc.asset_id = a.id
    ORDER BY rc.measured_at DESC
    LIMIT 1
) lr ON TRUE;

-- -----------------------------------------------------------------------------
-- Trigger: atualiza updated_at automaticamente em assets
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS assets_updated_at ON assets;
CREATE TRIGGER assets_updated_at
    BEFORE UPDATE ON assets
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_updated_at();
