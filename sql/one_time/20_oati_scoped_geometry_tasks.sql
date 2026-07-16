-- Migrate OATI order tasks to scoped geometry identity: oati_id = {point|line|polygon}:{id}
-- Disruption tasks (type «Разрытия») keep order_number in oati_id — not touched.
--
-- After this script: re-collect districts in WebCRM (or QGIS) to recreate OATI tasks.

BEGIN;

CREATE TEMP TABLE legacy_oati_order_tasks ON COMMIT DROP AS
SELECT key
FROM crm.tasks
WHERE type = 'Новые ордера ОАТИ, АВР и земляные работы'
  AND oati_id IS NOT NULL
  AND oati_id !~ '^(point|line|polygon):';

DELETE FROM crm.tasks_field WHERE task_key IN (SELECT key FROM legacy_oati_order_tasks);
DELETE FROM crm.tasks_done_legal WHERE task_key IN (SELECT key FROM legacy_oati_order_tasks);
DELETE FROM crm.tasks_done_illegal WHERE task_key IN (SELECT key FROM legacy_oati_order_tasks);
DELETE FROM crm.tasks_clear WHERE task_key IN (SELECT key FROM legacy_oati_order_tasks);

DELETE FROM crm.tasks WHERE key IN (SELECT key FROM legacy_oati_order_tasks);

COMMIT;

-- Re-collect districts via WebCRM UI → «Получить задачу» or persist_district_tasks.
