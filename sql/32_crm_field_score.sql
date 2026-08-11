-- Quality assessment scores for field-surveyed area orders.

CREATE SCHEMA IF NOT EXISTS crm;

CREATE TABLE IF NOT EXISTS crm.field_score (
    id                  BIGSERIAL PRIMARY KEY,
    order_key           UUID NOT NULL UNIQUE,
    task_scores         JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"<task_uuid>": "unsatisfactory"|"satisfactory"|"good"}
    track_coverage_pct  NUMERIC(5,2),
    order_score         TEXT
        CHECK (order_score IS NULL OR order_score IN
            ('unsatisfactory', 'satisfactory', 'good')),
    scored_by           TEXT NOT NULL,
    scored_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_field_score_scored_at
    ON crm.field_score (scored_at DESC);
