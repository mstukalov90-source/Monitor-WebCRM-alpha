-- Pause GenPlan (photo_uuid) task creation for a camera after send-to-field.
-- ETL INSERTs into crm.tasks are skipped silently while the block is active.

CREATE TABLE IF NOT EXISTS crm.camera_blocks (
    cam_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN (
        'until_field_observed',
        'until_quarter',
        'until_date',
        'until_order_end'
    )),
    until_date DATE,
    task_key UUID,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_camera_blocks_task_key
    ON crm.camera_blocks (task_key)
    WHERE task_key IS NOT NULL;

CREATE OR REPLACE FUNCTION crm.camera_is_blocked(p_cam_id TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  blk RECORD;
  observed BOOLEAN;
  today_msk DATE;
BEGIN
  IF p_cam_id IS NULL OR btrim(p_cam_id) = '' THEN
    RETURN FALSE;
  END IF;

  SELECT mode, until_date, task_key
    INTO blk
  FROM crm.camera_blocks
  WHERE cam_id = btrim(p_cam_id);

  IF NOT FOUND THEN
    RETURN FALSE;
  END IF;

  today_msk := (NOW() AT TIME ZONE 'Europe/Moscow')::date;

  IF blk.mode = 'until_field_observed' THEN
    IF blk.task_key IS NULL THEN
      RETURN TRUE;
    END IF;
    SELECT field_observed INTO observed
    FROM crm.tasks
    WHERE key = blk.task_key;
    RETURN COALESCE(observed, FALSE) IS NOT TRUE;
  END IF;

  IF blk.mode = 'until_quarter' THEN
    RETURN blk.until_date IS NOT NULL AND today_msk < blk.until_date;
  END IF;

  IF blk.mode IN ('until_date', 'until_order_end') THEN
    RETURN blk.until_date IS NOT NULL AND today_msk <= blk.until_date;
  END IF;

  RETURN FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION crm.camera_block_skip_task_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  cam TEXT;
BEGIN
  IF NEW.photo_uuid IS NULL OR btrim(NEW.photo_uuid) = '' THEN
    RETURN NEW;
  END IF;

  BEGIN
    SELECT NULLIF(btrim(cam_id::text), '')
      INTO cam
    FROM genplan.photo_meta
    WHERE uuid::text = btrim(NEW.photo_uuid)
    LIMIT 1;
  EXCEPTION
    WHEN undefined_table OR undefined_column THEN
      RETURN NEW;
  END;

  IF cam IS NULL THEN
    RETURN NEW;
  END IF;

  IF crm.camera_is_blocked(cam) THEN
    RAISE NOTICE
      'camera_blocks: skip INSERT crm.tasks photo_uuid=% cam_id=%',
      NEW.photo_uuid, cam;
    RETURN NULL;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_camera_block_skip_insert ON crm.tasks;
CREATE TRIGGER trg_camera_block_skip_insert
  BEFORE INSERT ON crm.tasks
  FOR EACH ROW
  EXECUTE FUNCTION crm.camera_block_skip_task_insert();

CREATE OR REPLACE FUNCTION crm.camera_block_release_on_observed()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.field_observed IS TRUE AND OLD.field_observed IS DISTINCT FROM TRUE THEN
    DELETE FROM crm.camera_blocks
    WHERE mode = 'until_field_observed'
      AND task_key = NEW.key;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_camera_block_release_observed ON crm.tasks;
CREATE TRIGGER trg_camera_block_release_observed
  BEFORE UPDATE OF field_observed ON crm.tasks
  FOR EACH ROW
  EXECUTE FUNCTION crm.camera_block_release_on_observed();
