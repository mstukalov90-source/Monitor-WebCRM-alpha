-- Restore point-based earthwork / local repair / AVR task identity.
-- Run once after deploying source_field=id and link_lookup_field in layers_config.
--
-- Legacy order tasks used registration_number (or global_id / em_call_reg_num) as earthwork_id.
-- New model: earthwork_id = numeric point id from items_*_points.
-- Disruption tasks (type «Разрытия») keep registration numbers in earthwork_id — not touched.
--
-- After this script: re-collect affected districts in WebCRM (or QGIS) to recreate tasks.

BEGIN;

CREATE TEMP TABLE legacy_order_tasks ON COMMIT DROP AS
SELECT key
FROM crm.tasks
WHERE type = 'Новые ордера ОАТИ, АВР и земляные работы'
  AND (
    (earthwork_id IS NOT NULL AND earthwork_id !~ '^[0-9]+$')
    OR (localwork_id IS NOT NULL AND localwork_id !~ '^[0-9]+$')
    OR (avr_mos_id IS NOT NULL AND avr_mos_id !~ '^[0-9]+$')
  );

DELETE FROM crm.tasks_field WHERE task_key IN (SELECT key FROM legacy_order_tasks);
DELETE FROM crm.tasks_done_legal WHERE task_key IN (SELECT key FROM legacy_order_tasks);
DELETE FROM crm.tasks_done_illegal WHERE task_key IN (SELECT key FROM legacy_order_tasks);
DELETE FROM crm.tasks_clear WHERE task_key IN (SELECT key FROM legacy_order_tasks);

DELETE FROM crm.tasks WHERE key IN (SELECT key FROM legacy_order_tasks);

COMMIT;

-- Re-collect example: district Сокол in WebCRM UI → «Получить задачу»
-- Expected for У0218899: 3 tasks with earthwork_id IN (2752, 2753, 2754).
