-- Statistics for office camera-analysis tasks (is_office_task = true).

CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT;
    v_action TEXT;
BEGIN
    IF COALESCE(NEW.is_field_data, false) IS TRUE THEN
        RETURN NEW;
    END IF;

    v_login := NULLIF(TRIM(NEW.user_created[1]), '');
    IF v_login IS NULL OR crm.statistics_resolve_role(v_login) <> 'office' THEN
        RETURN NEW;
    END IF;

    IF COALESCE(NEW.is_office_task, false) IS TRUE THEN
        v_action := 'task_created_office_analysis';
    ELSE
        v_action := 'task_created';
    END IF;

    PERFORM crm.statistics_insert_row(
        v_login,
        'office',
        'task',
        v_action,
        NEW.key,
        COALESCE((NEW.user_created[2])::timestamptz, NOW()),
        jsonb_build_object(
            'source', 'trigger',
            'task_type', NEW.type,
            'is_office_task', COALESCE(NEW.is_office_task, false)
        )
    );

    RETURN NEW;
END;
$$;

-- Remove misclassified task_created rows for camera-analysis tasks.
DELETE FROM crm.statistics s
WHERE s.action = 'task_created'
  AND s.object_type = 'task'
  AND EXISTS (
      SELECT 1
      FROM crm.tasks t
      WHERE t.key = s.object_key
        AND t.is_office_task IS TRUE
  );

-- Backfill historical camera-analysis task creations.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    t.user_created[1],
    'office',
    'task',
    'task_created_office_analysis',
    t.key,
    COALESCE((t.user_created[2])::timestamptz, NOW()),
    jsonb_build_object('source', 'backfill', 'is_office_task', true)
FROM crm.tasks t
JOIN crm.users u ON u.login = t.user_created[1]
  AND u.role IN ('office', 'manager', 'admin')
WHERE t.is_office_task IS TRUE
  AND t.user_created IS NOT NULL
  AND array_length(t.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1
      FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.action = 'task_created_office_analysis'
        AND s.object_key = t.key
  );
