-- Source anchor columns on crm.tasks for stable geometry links across ETL id changes.
-- Run after MONITOR/sql/27_data_mos_items_task_key.sql (task_key on items_* split tables).

ALTER TABLE crm.tasks
    ADD COLUMN IF NOT EXISTS source_global_id BIGINT,
    ADD COLUMN IF NOT EXISTS source_table TEXT,
    ADD COLUMN IF NOT EXISTS source_row_id BIGINT,
    ADD COLUMN IF NOT EXISTS source_geom_hash TEXT;

CREATE INDEX IF NOT EXISTS tasks_idx_source_anchor
    ON crm.tasks (source_global_id, source_geom_hash)
    WHERE source_global_id IS NOT NULL AND source_geom_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS tasks_idx_source_row
    ON crm.tasks (source_table, source_row_id)
    WHERE source_table IS NOT NULL AND source_row_id IS NOT NULL;
