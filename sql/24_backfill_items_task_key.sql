-- Backfill data_mos.items_* split tables with task_key from existing scoped business ids.
-- Requires MONITOR/sql/27_data_mos_items_task_key.sql.
-- Safe to re-run: only fills rows where task_key IS NULL.

-- OATI (items_2855)
UPDATE data_mos.items_2855_points t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.oati_id = 'point:' || TRIM(t.id::text);

UPDATE data_mos.items_2855_lines t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.oati_id = 'line:' || TRIM(t.id::text);

UPDATE data_mos.items_2855_polygons t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.oati_id = 'polygon:' || TRIM(t.id::text);

-- Earthwork (items_62501)
UPDATE data_mos.items_62501_points t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.earthwork_id = 'point:' || TRIM(t.id::text);

UPDATE data_mos.items_62501_lines t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.earthwork_id = 'line:' || TRIM(t.id::text);

UPDATE data_mos.items_62501_polygons t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.earthwork_id = 'polygon:' || TRIM(t.id::text);

-- Localwork (items_62441)
UPDATE data_mos.items_62441_points t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.localwork_id = 'point:' || TRIM(t.id::text);

UPDATE data_mos.items_62441_lines t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.localwork_id = 'line:' || TRIM(t.id::text);

UPDATE data_mos.items_62441_polygons t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.localwork_id = 'polygon:' || TRIM(t.id::text);

-- AVR (items_62461)
UPDATE data_mos.items_62461_points t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.avr_mos_id = 'point:' || TRIM(t.id::text);

UPDATE data_mos.items_62461_lines t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.avr_mos_id = 'line:' || TRIM(t.id::text);

UPDATE data_mos.items_62461_polygons t
SET task_key = ct.key
FROM crm.tasks ct
WHERE t.task_key IS NULL AND ct.avr_mos_id = 'polygon:' || TRIM(t.id::text);

-- Backfill source anchors on crm.tasks from linked items rows.
UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_2855_points',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_2855_points t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.oati_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_2855_lines',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_2855_lines t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.oati_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_2855_polygons',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_2855_polygons t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.oati_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62501_points',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62501_points t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.earthwork_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62501_lines',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62501_lines t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.earthwork_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62501_polygons',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62501_polygons t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.earthwork_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62441_points',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62441_points t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.localwork_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62441_lines',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62441_lines t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.localwork_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62441_polygons',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62441_polygons t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.localwork_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62461_points',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62461_points t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.avr_mos_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62461_lines',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62461_lines t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.avr_mos_id IS NOT NULL;

UPDATE crm.tasks ct SET
    source_table = 'data_mos.items_62461_polygons',
    source_row_id = t.id,
    source_global_id = t.global_id,
    source_geom_hash = md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(t.geom), 4326)))
FROM data_mos.items_62461_polygons t
WHERE t.task_key = ct.key AND ct.source_row_id IS NULL AND ct.avr_mos_id IS NOT NULL;
