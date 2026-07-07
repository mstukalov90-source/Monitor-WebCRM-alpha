-- Link health report: orphan tasks, orphan task_key rows, duplicate geom_hash anchors.
-- Run manually or via scripts/link_health_check.sh after ETL / backfill.

-- Orphan tasks: scoped id present but no matching items row with task_key
SELECT 'orphan_task' AS issue,
       ct.key::text AS task_key,
       COALESCE(ct.oati_id, ct.earthwork_id, ct.localwork_id, ct.avr_mos_id) AS business_id,
       ct.source_table,
       ct.source_row_id
FROM crm.tasks ct
WHERE (
    ct.oati_id IS NOT NULL
    OR ct.earthwork_id IS NOT NULL
    OR ct.localwork_id IS NOT NULL
    OR ct.avr_mos_id IS NOT NULL
)
AND NOT EXISTS (
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
)
AND ct.is_field_data IS NOT TRUE
AND ct.is_office_task IS NOT TRUE;

-- Orphan task_key: items row linked to missing crm.tasks
SELECT 'orphan_task_key' AS issue,
       t.task_key::text,
       'data_mos.' || relname AS source_table,
       t.id AS source_row_id
FROM (
    SELECT task_key, id, 'items_2855_points' AS relname FROM data_mos.items_2855_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_2855_lines' FROM data_mos.items_2855_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_2855_polygons' FROM data_mos.items_2855_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62501_points' FROM data_mos.items_62501_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62501_lines' FROM data_mos.items_62501_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62501_polygons' FROM data_mos.items_62501_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62441_points' FROM data_mos.items_62441_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62441_lines' FROM data_mos.items_62441_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62441_polygons' FROM data_mos.items_62441_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62461_points' FROM data_mos.items_62461_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62461_lines' FROM data_mos.items_62461_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key, id, 'items_62461_polygons' FROM data_mos.items_62461_polygons WHERE task_key IS NOT NULL
) t
LEFT JOIN crm.tasks ct ON ct.key = t.task_key
WHERE ct.key IS NULL;

-- Duplicate source anchors (same global_id + geom_hash -> multiple tasks)
SELECT 'duplicate_anchor' AS issue,
       source_global_id,
       source_geom_hash,
       COUNT(*) AS task_count
FROM crm.tasks
WHERE source_global_id IS NOT NULL
  AND source_geom_hash IS NOT NULL
GROUP BY source_global_id, source_geom_hash
HAVING COUNT(*) > 1;

-- Summary counts
SELECT 'linked_items' AS metric, COUNT(*) AS cnt FROM (
    SELECT task_key FROM data_mos.items_2855_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_2855_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_2855_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62501_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62501_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62501_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62441_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62441_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62441_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62461_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62461_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62461_polygons WHERE task_key IS NOT NULL
) s;
