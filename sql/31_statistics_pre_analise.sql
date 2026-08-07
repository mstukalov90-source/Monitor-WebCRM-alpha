-- Pre-analise stage columns + statistics triggers + backfill.

ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise BOOLEAN;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise_started_by TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise_started_at TIMESTAMPTZ;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise_finished_by TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise_finished_at TIMESTAMPTZ;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise_paused_by TEXT;
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS pre_analise_paused_at TIMESTAMPTZ;

-- Office: pre_analise started / completed.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_area_pre_analise()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.pre_analise_started_at IS NULL
       AND NEW.pre_analise_started_at IS NOT NULL
       AND NULLIF(TRIM(NEW.pre_analise_started_by), '') IS NOT NULL
    THEN
        PERFORM crm.statistics_emit_office_event(
            'office_pre_analise_started',
            'order',
            NEW.key,
            NEW.pre_analise_started_by,
            NEW.pre_analise_started_at,
            jsonb_build_object('source', 'trigger', 'rayon', NEW.rayon)
        );
    END IF;

    IF (
        (COALESCE(OLD.pre_analise, false) IS DISTINCT FROM TRUE AND NEW.pre_analise IS TRUE)
        OR (OLD.pre_analise_finished_at IS NULL AND NEW.pre_analise_finished_at IS NOT NULL)
    )
    AND NULLIF(TRIM(NEW.pre_analise_finished_by), '') IS NOT NULL
    THEN
        PERFORM crm.statistics_emit_office_event(
            'office_pre_analise_completed',
            'order',
            NEW.key,
            NEW.pre_analise_finished_by,
            COALESCE(NEW.pre_analise_finished_at, NOW()),
            jsonb_build_object('source', 'trigger', 'rayon', NEW.rayon)
        );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_area_pre_analise ON crm.tasks_area;
CREATE TRIGGER trg_statistics_tasks_area_pre_analise
    AFTER UPDATE OF pre_analise, pre_analise_started_at, pre_analise_started_by,
                    pre_analise_finished_at, pre_analise_finished_by
    ON crm.tasks_area
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_area_pre_analise();

-- Backfill: pre_analise started.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    ta.pre_analise_started_by,
    'office',
    'order',
    'office_pre_analise_started',
    ta.key,
    ta.pre_analise_started_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.pre_analise_started_by
  AND u.role IN ('office', 'manager', 'admin')
WHERE ta.pre_analise_started_at IS NOT NULL
  AND NULLIF(TRIM(ta.pre_analise_started_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order'
        AND s.object_key = ta.key
        AND s.action = 'office_pre_analise_started'
  );

-- Backfill: pre_analise completed.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    ta.pre_analise_finished_by,
    'office',
    'order',
    'office_pre_analise_completed',
    ta.key,
    ta.pre_analise_finished_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.pre_analise_finished_by
  AND u.role IN ('office', 'manager', 'admin')
WHERE ta.pre_analise_finished_at IS NOT NULL
  AND NULLIF(TRIM(ta.pre_analise_finished_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order'
        AND s.object_key = ta.key
        AND s.action = 'office_pre_analise_completed'
  );
