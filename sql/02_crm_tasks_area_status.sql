-- Добавить status и date_survey в crm.tasks_area

ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS date_survey DATE;

UPDATE crm.tasks_area
SET status = (ARRAY['done', 'wip', 'free'])[1 + floor(random() * 3)::int]
WHERE status IS NULL;
