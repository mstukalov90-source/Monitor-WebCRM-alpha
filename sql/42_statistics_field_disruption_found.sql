-- Field disruption found: emit without a 5-minute report window, on INSERT and
-- on UPDATE is_field_data false→true; do not classify a report as camera survey
-- before the crm.tasks row exists. Backfill missing field_disruption_found rows.
--
-- WRITE SURFACE: CREATE OR REPLACE functions/triggers; INSERT/DELETE on
-- crm.statistics ONLY. Do not INSERT/UPDATE/DELETE crm.tasks, tasks_field,
-- tasks_clear, tasks_done_legal, tasks_done_illegal, or tasks_area.

-- Field: disruption found when field-data task is created or flagged, with any report.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_field_data_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_at TIMESTAMPTZ;
    v_login TEXT;
    v_report_username TEXT;
    v_report_at TIMESTAMPTZ;
BEGIN
    IF COALESCE(NEW.is_field_data, false) IS NOT TRUE THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' AND COALESCE(OLD.is_field_data, false) IS TRUE THEN
        RETURN NEW;
    END IF;

    SELECT NULLIF(TRIM(r.username), ''), r.created_at
    INTO v_report_username, v_report_at
    FROM mggt_field.reports r
    WHERE r.tasks_key = NEW.key
      AND NULLIF(TRIM(r.username), '') IS NOT NULL
    ORDER BY r.created_at DESC
    LIMIT 1;

    -- No report yet: reports-insert trigger will emit when the report arrives.
    IF v_report_username IS NULL THEN
        RETURN NEW;
    END IF;

    v_login := COALESCE(
        v_report_username,
        crm.statistics_audit_login(NEW.user_created)
    );
    IF v_login IS NULL THEN
        RETURN NEW;
    END IF;

    v_at := COALESCE(
        v_report_at,
        crm.statistics_audit_at(NEW.user_created, NOW()),
        NOW()
    );

    PERFORM crm.statistics_emit_field_event(
        'field_disruption_found',
        NEW.key,
        v_login,
        v_at,
        jsonb_build_object(
            'source', 'trigger',
            'via', CASE
                WHEN TG_OP = 'UPDATE' THEN 'tasks_update_field_data'
                ELSE 'tasks_insert_field_data'
            END
        )
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_field_data_insert ON crm.tasks;
CREATE TRIGGER trg_statistics_tasks_field_data_insert
    AFTER INSERT ON crm.tasks
    FOR EACH ROW
    WHEN (NEW.is_field_data IS TRUE)
    EXECUTE FUNCTION crm.trg_statistics_tasks_field_data_insert();

DROP TRIGGER IF EXISTS trg_statistics_tasks_field_data_update ON crm.tasks;
CREATE TRIGGER trg_statistics_tasks_field_data_update
    AFTER UPDATE OF is_field_data ON crm.tasks
    FOR EACH ROW
    WHEN (NEW.is_field_data IS TRUE AND OLD.is_field_data IS DISTINCT FROM TRUE)
    EXECUTE FUNCTION crm.trg_statistics_tasks_field_data_insert();

-- Field: report + companion events. Do not emit camera survey when the task
-- row does not exist yet (field client often inserts the report first).
CREATE OR REPLACE FUNCTION crm.trg_statistics_reports_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT;
    v_at TIMESTAMPTZ;
    v_task_exists BOOLEAN;
BEGIN
    IF NEW.tasks_key IS NULL OR NULLIF(TRIM(NEW.username), '') IS NULL THEN
        RETURN NEW;
    END IF;

    v_at := COALESCE(NEW.created_at, NOW());
    v_login := NULLIF(TRIM(NEW.username), '');

    IF EXISTS (
        SELECT 1 FROM crm.tasks_clear c WHERE c.task_key = NEW.tasks_key
    ) THEN
        PERFORM crm.statistics_emit_field_event(
            'field_disruption_absent',
            NEW.tasks_key,
            v_login,
            v_at,
            jsonb_build_object('source', 'trigger', 'via', 'reports_insert')
        );
        RETURN NEW;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM crm.tasks t
        WHERE t.key = NEW.tasks_key
          AND COALESCE(t.is_field_data, false) IS TRUE
    ) THEN
        PERFORM crm.statistics_emit_field_event(
            'field_disruption_found',
            NEW.tasks_key,
            v_login,
            v_at,
            jsonb_build_object('source', 'trigger', 'via', 'reports_insert')
        );
        RETURN NEW;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM crm.tasks t WHERE t.key = NEW.tasks_key
    ) INTO v_task_exists;

    IF NOT v_task_exists THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM crm.tasks_field tf WHERE tf.task_key = NEW.tasks_key
    ) THEN
        PERFORM crm.statistics_emit_field_event(
            'field_camera_survey',
            NEW.tasks_key,
            v_login,
            v_at,
            jsonb_build_object('source', 'trigger', 'via', 'reports_insert')
        );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_reports_insert ON mggt_field.reports;
CREATE TRIGGER trg_statistics_reports_insert
    AFTER INSERT ON mggt_field.reports
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_reports_insert();

-- Backfill: field_disruption_found for existing is_field_data tasks with a field report.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT DISTINCT ON (t.key)
    u.uuid,
    r.username,
    'field',
    'task',
    'field_disruption_found',
    t.key,
    COALESCE(r.created_at, crm.statistics_audit_at(t.user_created, NOW())),
    jsonb_build_object('source', 'backfill', 'via', 'report_and_field_data_task')
FROM crm.tasks t
JOIN mggt_field.reports r ON r.tasks_key = t.key
JOIN crm.users u ON u.login = r.username AND u.role = 'field'
WHERE t.is_field_data IS TRUE
  AND NULLIF(TRIM(r.username), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = t.key
        AND s.action = 'field_disruption_found'
  )
ORDER BY t.key, r.created_at DESC;

-- Remove camera-survey rows that were misclassified for field-data discoveries.
DELETE FROM crm.statistics s
WHERE s.object_type = 'task'
  AND s.action = 'field_camera_survey'
  AND EXISTS (
      SELECT 1
      FROM crm.tasks t
      WHERE t.key = s.object_key
        AND t.is_field_data IS TRUE
  );
