-- Remove link-orphan crm.tasks (no items_* row with task_key) and duplicate source anchors.
-- Safe pattern: delete snapshots first, then tasks. Re-collect districts after scoped orphans removed.
--
-- Orphan categories:
--   legacy non-scoped business id (order_number / notification text in oati_id/earthwork_id)
--   scoped id but items row missing (stale after pre-merge ETL)
--   duplicate anchor: keep task linked on items, drop the other

BEGIN;

CREATE TEMP TABLE items_link_exists ON COMMIT DROP AS
SELECT ct.key
FROM crm.tasks ct
WHERE EXISTS (
    SELECT 1 FROM data_mos.items_2855_points t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_2855_lines t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_2855_polygons t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62501_points t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62501_lines t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62501_polygons t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62441_points t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62441_lines t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62441_polygons t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62461_points t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62461_lines t WHERE t.task_key = ct.key
    UNION ALL SELECT 1 FROM data_mos.items_62461_polygons t WHERE t.task_key = ct.key
);

CREATE TEMP TABLE link_orphan_tasks ON COMMIT DROP AS
SELECT ct.key
FROM crm.tasks ct
WHERE ct.is_field_data IS NOT TRUE
  AND ct.is_office_task IS NOT TRUE
  AND (
      ct.oati_id IS NOT NULL
      OR ct.earthwork_id IS NOT NULL
      OR ct.localwork_id IS NOT NULL
      OR ct.avr_mos_id IS NOT NULL
  )
  AND ct.key NOT IN (SELECT key FROM items_link_exists)
  AND (
      (ct.oati_id IS NOT NULL AND ct.oati_id !~ '^(point|line|polygon):')
      OR (ct.earthwork_id IS NOT NULL AND ct.earthwork_id !~ '^(point|line|polygon):')
      OR (ct.localwork_id IS NOT NULL AND ct.localwork_id !~ '^(point|line|polygon):')
      OR (ct.avr_mos_id IS NOT NULL AND ct.avr_mos_id !~ '^(point|line|polygon):')
      OR (ct.oati_id ~ '^(point|line|polygon):')
      OR (ct.earthwork_id ~ '^(point|line|polygon):')
      OR (ct.localwork_id ~ '^(point|line|polygon):')
      OR (ct.avr_mos_id ~ '^(point|line|polygon):')
  );

-- Duplicate anchor: same global_id + geom_hash, keep row with items link or lower key
CREATE TEMP TABLE duplicate_anchor_drop ON COMMIT DROP AS
SELECT dup.key
FROM (
    SELECT ct.key,
           ROW_NUMBER() OVER (
               PARTITION BY ct.source_global_id, ct.source_geom_hash
               ORDER BY
                   CASE WHEN ct.key IN (SELECT key FROM items_link_exists) THEN 0 ELSE 1 END,
                   ct.key
           ) AS rn
    FROM crm.tasks ct
    WHERE ct.source_global_id IS NOT NULL
      AND ct.source_geom_hash IS NOT NULL
) dup
WHERE dup.rn > 1;

CREATE TEMP TABLE tasks_to_delete ON COMMIT DROP AS
SELECT key FROM link_orphan_tasks
UNION
SELECT key FROM duplicate_anchor_drop;

SELECT 'orphans_to_delete' AS metric, COUNT(*)::text AS value FROM link_orphan_tasks
UNION ALL
SELECT 'duplicate_anchor_to_delete', COUNT(*)::text FROM duplicate_anchor_drop
UNION ALL
SELECT 'total_to_delete', COUNT(*)::text FROM tasks_to_delete;

DELETE FROM crm.tasks_field WHERE task_key IN (SELECT key FROM tasks_to_delete);
DELETE FROM crm.tasks_done_legal WHERE task_key IN (SELECT key FROM tasks_to_delete);
DELETE FROM crm.tasks_done_illegal WHERE task_key IN (SELECT key FROM tasks_to_delete);
DELETE FROM crm.tasks_clear WHERE task_key IN (SELECT key FROM tasks_to_delete);

DELETE FROM crm.tasks WHERE key IN (SELECT key FROM tasks_to_delete);

COMMIT;
