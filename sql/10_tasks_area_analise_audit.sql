-- Аудит анализа площадного заказа (office workflow)
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise_started_by TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise_started_at TIMESTAMPTZ;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise_finished_by TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise_finished_at TIMESTAMPTZ;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise_paused_by TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise_paused_at TIMESTAMPTZ;
