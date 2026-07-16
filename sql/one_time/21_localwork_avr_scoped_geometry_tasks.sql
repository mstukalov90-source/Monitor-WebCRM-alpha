-- Migrate localwork / AVR order tasks to scoped geometry identity:
--   localwork_id / avr_mos_id = {point|line|polygon}:{id}
-- Disruption tasks (type «Разрытия») are NOT touched.
-- Does NOT touch earthwork_id / oati_id (already scoped).
--
-- Migration 19 only rewrites numeric ids matching items_* .id; legacy rows
-- stored global_id (localwork) or em_call_reg_num (AVR) are removed here.
--
-- Before running: sql/db_crm_legacy_localwork_avr_inventory.sql (MONITOR_QGIS)
-- After this script: re-collect districts in WebCRM (or QGIS) to recreate tasks.

BEGIN;

CREATE TEMP TABLE legacy_localwork_avr_order_tasks ON COMMIT DROP AS
SELECT key
FROM crm.tasks
WHERE type = 'Новые ордера ОАТИ, АВР и земляные работы'
  AND (
      (localwork_id IS NOT NULL AND localwork_id !~ '^(point|line|polygon):')
      OR (avr_mos_id IS NOT NULL AND avr_mos_id !~ '^(point|line|polygon):')
  );

DELETE FROM crm.tasks_field WHERE task_key IN (SELECT key FROM legacy_localwork_avr_order_tasks);
DELETE FROM crm.tasks_done_legal WHERE task_key IN (SELECT key FROM legacy_localwork_avr_order_tasks);
DELETE FROM crm.tasks_done_illegal WHERE task_key IN (SELECT key FROM legacy_localwork_avr_order_tasks);
DELETE FROM crm.tasks_clear WHERE task_key IN (SELECT key FROM legacy_localwork_avr_order_tasks);

DELETE FROM crm.tasks WHERE key IN (SELECT key FROM legacy_localwork_avr_order_tasks);

COMMIT;

-- Re-collect districts via WebCRM UI → «Получить задачу» or QGIS persist.
