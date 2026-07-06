-- Migrate numeric geometry ids to scoped form: {geometry_type}:{id}
-- Run once before re-collecting districts for line/polygon tasks.

BEGIN;

UPDATE crm.tasks t
SET earthwork_id = 'point:' || t.earthwork_id
WHERE t.earthwork_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62501_points p
    WHERE p.id::text = t.earthwork_id
  );

UPDATE crm.tasks t
SET earthwork_id = 'line:' || t.earthwork_id
WHERE t.earthwork_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62501_lines l
    WHERE l.id::text = t.earthwork_id
  );

UPDATE crm.tasks t
SET earthwork_id = 'polygon:' || t.earthwork_id
WHERE t.earthwork_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62501_polygons g
    WHERE g.id::text = t.earthwork_id
  );

UPDATE crm.tasks t
SET localwork_id = 'point:' || t.localwork_id
WHERE t.localwork_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62441_points p
    WHERE p.id::text = t.localwork_id
  );

UPDATE crm.tasks t
SET localwork_id = 'line:' || t.localwork_id
WHERE t.localwork_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62441_lines l
    WHERE l.id::text = t.localwork_id
  );

UPDATE crm.tasks t
SET localwork_id = 'polygon:' || t.localwork_id
WHERE t.localwork_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62441_polygons g
    WHERE g.id::text = t.localwork_id
  );

UPDATE crm.tasks t
SET avr_mos_id = 'point:' || t.avr_mos_id
WHERE t.avr_mos_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62461_points p
    WHERE p.id::text = t.avr_mos_id
  );

UPDATE crm.tasks t
SET avr_mos_id = 'line:' || t.avr_mos_id
WHERE t.avr_mos_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62461_lines l
    WHERE l.id::text = t.avr_mos_id
  );

UPDATE crm.tasks t
SET avr_mos_id = 'polygon:' || t.avr_mos_id
WHERE t.avr_mos_id ~ '^[0-9]+$'
  AND EXISTS (
    SELECT 1 FROM data_mos.items_62461_polygons g
    WHERE g.id::text = t.avr_mos_id
  );

COMMIT;

-- Re-collect districts in WebCRM to create line/polygon tasks (e.g. Сокол / У0218899).
