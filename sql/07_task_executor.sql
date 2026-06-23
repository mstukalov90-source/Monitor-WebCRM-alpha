-- Task executor assignment (login from crm.users) for field personnel management.

ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS executor TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS executor TEXT;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_field_executor
    ON crm.tasks_field (executor);
CREATE INDEX IF NOT EXISTS idx_crm_tasks_area_executor
    ON crm.tasks_area (executor);
