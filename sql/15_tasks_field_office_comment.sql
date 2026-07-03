-- Необязательный комментарий камерального анализа при отправке задачи в поле
ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS office_comment TEXT;
