-- Rayon сессии при отправке задачи «В поле».
-- Legacy-строки с rayon IS NULL отображаются через geometry∩район (fallback).

ALTER TABLE crm.tasks_field
    ADD COLUMN IF NOT EXISTS rayon TEXT;

CREATE INDEX IF NOT EXISTS idx_tasks_field_rayon
    ON crm.tasks_field (rayon)
    WHERE rayon IS NOT NULL;
