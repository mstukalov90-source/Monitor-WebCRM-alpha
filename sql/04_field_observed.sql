-- field_observed: полевое обследование (read-only в CRM UI)

ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;

ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
ALTER TABLE crm.tasks_clear ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
