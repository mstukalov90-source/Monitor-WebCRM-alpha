-- Номер задачи в crm.tasks_area

ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS task_number TEXT;
