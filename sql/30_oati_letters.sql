-- OATI incident letters metadata (DOCX itself is not stored).

CREATE SCHEMA IF NOT EXISTS webcrm;

CREATE TABLE IF NOT EXISTS webcrm.oati_letters (
    fid          BIGSERIAL PRIMARY KEY,
    task_key     UUID NOT NULL,
    report_id    BIGINT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_webcrm_oati_letters_task_report
    ON webcrm.oati_letters (task_key, report_id);

CREATE INDEX IF NOT EXISTS idx_webcrm_oati_letters_created_at
    ON webcrm.oati_letters (created_at DESC);
