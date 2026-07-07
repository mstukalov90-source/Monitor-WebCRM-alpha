-- Remove tasks_field.geom: geometry always resolved from items_* by task_key.
DROP INDEX IF EXISTS crm.tasks_field_geom_gix;
ALTER TABLE crm.tasks_field DROP COLUMN IF EXISTS geom;
