-- Маркер задач «Полевые данные» (сохраняется после заполнения сопоставления)
ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS is_field_data BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS is_field_data BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS is_field_data BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS is_field_data BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_clear ADD COLUMN IF NOT EXISTS is_field_data BOOLEAN NOT NULL DEFAULT false;
