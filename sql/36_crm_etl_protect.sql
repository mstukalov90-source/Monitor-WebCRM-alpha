-- ETL protect pin for transferred KosolapovRS task keys.
-- Blocks DELETE / field_observed clear / report rekey for rows in crm.etl_protect.
-- Does NOT touch crm.tasks_area (ETL never writes it).

CREATE TABLE IF NOT EXISTS crm.etl_protect (
  object_key UUID PRIMARY KEY,
  object_kind TEXT NOT NULL CHECK (object_kind = 'task'),
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION crm.etl_protect_block_task_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM crm.etl_protect p WHERE p.object_key = OLD.key
  ) THEN
    RAISE EXCEPTION 'etl_protect: DELETE blocked for crm.tasks.key=%', OLD.key;
  END IF;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_etl_protect_task_delete ON crm.tasks;
CREATE TRIGGER trg_etl_protect_task_delete
  BEFORE DELETE ON crm.tasks
  FOR EACH ROW
  EXECUTE FUNCTION crm.etl_protect_block_task_delete();

CREATE OR REPLACE FUNCTION crm.etl_protect_block_unobserve()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM crm.etl_protect p WHERE p.object_key = NEW.key
  ) AND NEW.field_observed IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION
      'etl_protect: clearing field_observed blocked for crm.tasks.key=%',
      NEW.key;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_etl_protect_unobserve ON crm.tasks;
CREATE TRIGGER trg_etl_protect_unobserve
  BEFORE UPDATE OF field_observed ON crm.tasks
  FOR EACH ROW
  EXECUTE FUNCTION crm.etl_protect_block_unobserve();

CREATE OR REPLACE FUNCTION crm.etl_protect_block_clear_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM crm.etl_protect p WHERE p.object_key = OLD.task_key
  ) THEN
    RAISE EXCEPTION
      'etl_protect: DELETE blocked for crm.tasks_clear.task_key=%',
      OLD.task_key;
  END IF;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_etl_protect_clear_delete ON crm.tasks_clear;
CREATE TRIGGER trg_etl_protect_clear_delete
  BEFORE DELETE ON crm.tasks_clear
  FOR EACH ROW
  EXECUTE FUNCTION crm.etl_protect_block_clear_delete();

CREATE OR REPLACE FUNCTION crm.etl_protect_block_report_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.tasks_key IS NOT NULL AND EXISTS (
    SELECT 1 FROM crm.etl_protect p WHERE p.object_key = OLD.tasks_key
  ) THEN
    RAISE EXCEPTION
      'etl_protect: DELETE blocked for mggt_field.reports.tasks_key=%',
      OLD.tasks_key;
  END IF;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_etl_protect_report_delete ON mggt_field.reports;
CREATE TRIGGER trg_etl_protect_report_delete
  BEFORE DELETE ON mggt_field.reports
  FOR EACH ROW
  EXECUTE FUNCTION crm.etl_protect_block_report_delete();

CREATE OR REPLACE FUNCTION crm.etl_protect_block_report_rekey()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.tasks_key IS DISTINCT FROM NEW.tasks_key
     AND (
       EXISTS (SELECT 1 FROM crm.etl_protect p WHERE p.object_key = OLD.tasks_key)
       OR EXISTS (SELECT 1 FROM crm.etl_protect p WHERE p.object_key = NEW.tasks_key)
     ) THEN
    RAISE EXCEPTION
      'etl_protect: tasks_key change blocked for report id=% (% -> %)',
      OLD.id, OLD.tasks_key, NEW.tasks_key;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_etl_protect_report_rekey ON mggt_field.reports;
CREATE TRIGGER trg_etl_protect_report_rekey
  BEFORE UPDATE OF tasks_key ON mggt_field.reports
  FOR EACH ROW
  EXECUTE FUNCTION crm.etl_protect_block_report_rekey();

-- Split-table DELETE guard: refuse deleting a row that still carries a protect task_key.
-- Normal ETL only deletes WHERE task_key IS NULL, so this does not block nightly split rebuild.
CREATE OR REPLACE FUNCTION crm.etl_protect_block_split_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.task_key IS NOT NULL AND EXISTS (
    SELECT 1 FROM crm.etl_protect p WHERE p.object_key = OLD.task_key
  ) THEN
    RAISE EXCEPTION
      'etl_protect: DELETE blocked for %.task_key=%',
      TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, OLD.task_key;
  END IF;
  RETURN OLD;
END;
$$;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'items_2855_points','items_2855_lines','items_2855_polygons',
    'items_62501_points','items_62501_lines','items_62501_polygons',
    'items_62441_points','items_62441_lines','items_62441_polygons',
    'items_62461_points','items_62461_lines','items_62461_polygons'
  ]
  LOOP
    EXECUTE format(
      'DROP TRIGGER IF EXISTS trg_etl_protect_split_delete ON data_mos.%I',
      t
    );
    EXECUTE format(
      'CREATE TRIGGER trg_etl_protect_split_delete
         BEFORE DELETE ON data_mos.%I
         FOR EACH ROW
         EXECUTE FUNCTION crm.etl_protect_block_split_delete()',
      t
    );
  END LOOP;
END $$;
