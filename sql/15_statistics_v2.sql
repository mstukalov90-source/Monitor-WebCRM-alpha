-- Statistics v2: 4 field + 6 office events, DB triggers (QGIS-ready).

CREATE OR REPLACE FUNCTION crm.statistics_audit_login(p_audit TEXT[])
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT NULLIF(TRIM(p_audit[1]), '');
$$;

CREATE OR REPLACE FUNCTION crm.statistics_audit_at(
    p_audit TEXT[],
    p_fallback TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TIMESTAMPTZ
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        NULLIF(TRIM(p_audit[2]), '')::timestamptz,
        p_fallback
    );
$$;

CREATE OR REPLACE FUNCTION crm.statistics_match_report(
    p_task_key UUID,
    p_window INTERVAL DEFAULT INTERVAL '5 minutes',
    p_reference_at TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (report_username TEXT, report_at TIMESTAMPTZ)
LANGUAGE sql
STABLE
AS $$
    SELECT
        NULLIF(TRIM(r.username), '') AS report_username,
        r.created_at AS report_at
    FROM mggt_field.reports r
    WHERE r.tasks_key = p_task_key
      AND NULLIF(TRIM(r.username), '') IS NOT NULL
      AND r.created_at >= p_reference_at - p_window
      AND r.created_at <= p_reference_at + p_window
    ORDER BY r.created_at DESC
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION crm.statistics_has_field_report(p_task_key UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM mggt_field.reports r
        WHERE r.tasks_key = p_task_key
          AND NULLIF(TRIM(r.username), '') IS NOT NULL
    );
$$;

CREATE OR REPLACE FUNCTION crm.statistics_emit_field_event(
    p_action TEXT,
    p_task_key UUID,
    p_login TEXT,
    p_created_at TIMESTAMPTZ DEFAULT NOW(),
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT := NULLIF(TRIM(p_login), '');
BEGIN
    IF v_login IS NULL OR p_task_key IS NULL THEN
        RETURN;
    END IF;

    IF crm.statistics_resolve_role(v_login) <> 'field' THEN
        RETURN;
    END IF;

    PERFORM crm.statistics_insert_row(
        v_login,
        'field',
        'task',
        p_action,
        p_task_key,
        COALESCE(p_created_at, NOW()),
        COALESCE(p_metadata, '{}'::jsonb)
    );
END;
$$;

CREATE OR REPLACE FUNCTION crm.statistics_emit_office_event(
    p_action TEXT,
    p_object_type TEXT,
    p_object_key UUID,
    p_login TEXT,
    p_created_at TIMESTAMPTZ DEFAULT NOW(),
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT := NULLIF(TRIM(p_login), '');
BEGIN
    IF v_login IS NULL OR p_object_key IS NULL THEN
        RETURN;
    END IF;

    IF crm.statistics_resolve_role(v_login) <> 'office' THEN
        RETURN;
    END IF;

    PERFORM crm.statistics_insert_row(
        v_login,
        'office',
        p_object_type,
        p_action,
        p_object_key,
        COALESCE(p_created_at, NOW()),
        COALESCE(p_metadata, '{}'::jsonb)
    );
END;
$$;

-- Field: report + companion events (bidirectional correlation).
CREATE OR REPLACE FUNCTION crm.trg_statistics_reports_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT;
    v_at TIMESTAMPTZ;
    v_match RECORD;
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

-- Field: camera survey when removed from tasks_field after report.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_field_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT;
    v_at TIMESTAMPTZ;
    v_report_username TEXT;
BEGIN
    IF current_setting('crm.statistics_skip_field_complete', true) = 'true' THEN
        RETURN OLD;
    END IF;

    IF NOT crm.statistics_has_field_report(OLD.task_key) THEN
        RETURN OLD;
    END IF;

    SELECT r.username, r.created_at
    INTO v_report_username, v_at
    FROM mggt_field.reports r
    WHERE r.tasks_key = OLD.task_key
    ORDER BY r.created_at DESC
    LIMIT 1;

    v_login := COALESCE(
        NULLIF(TRIM(OLD.executor), ''),
        NULLIF(TRIM(v_report_username), '')
    );

    PERFORM crm.statistics_emit_field_event(
        'field_camera_survey',
        OLD.task_key,
        v_login,
        COALESCE(v_at, NOW()),
        jsonb_build_object('source', 'trigger', 'via', 'tasks_field_delete', 'snapshot_key', OLD.key::text)
    );

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_field_delete ON crm.tasks_field;
CREATE TRIGGER trg_statistics_tasks_field_delete
    AFTER DELETE ON crm.tasks_field
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_field_delete();

-- Field / office: tasks_clear insert.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_clear_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_at TIMESTAMPTZ;
    v_login TEXT;
    v_match RECORD;
BEGIN
    v_at := COALESCE(
        crm.statistics_audit_at(NEW.user_created, COALESCE(NEW.sent_at, NOW())),
        NOW()
    );

    SELECT m.report_username, m.report_at
    INTO v_match
    FROM crm.statistics_match_report(NEW.task_key, INTERVAL '5 minutes', v_at) m;

    IF v_match.report_username IS NOT NULL THEN
        PERFORM crm.statistics_emit_field_event(
            'field_disruption_absent',
            NEW.task_key,
            v_match.report_username,
            COALESCE(v_match.report_at, v_at),
            jsonb_build_object('source', 'trigger', 'via', 'tasks_clear_insert')
        );
        RETURN NEW;
    END IF;

    v_login := crm.statistics_audit_login(NEW.user_created);
    PERFORM crm.statistics_emit_office_event(
        'office_disruption_absent',
        'task',
        NEW.task_key,
        v_login,
        v_at,
        jsonb_build_object('source', 'trigger', 'via', 'tasks_clear_insert')
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_clear_insert ON crm.tasks_clear;
CREATE TRIGGER trg_statistics_tasks_clear_insert
    AFTER INSERT ON crm.tasks_clear
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_clear_insert();

-- Field: disruption found when field-data task created with report.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_field_data_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_at TIMESTAMPTZ;
    v_match RECORD;
BEGIN
    IF COALESCE(NEW.is_field_data, false) IS NOT TRUE THEN
        RETURN NEW;
    END IF;

    v_at := crm.statistics_audit_at(NEW.user_created, NOW());

    SELECT m.report_username, m.report_at
    INTO v_match
    FROM crm.statistics_match_report(NEW.key, INTERVAL '5 minutes', v_at) m;

    IF v_match.report_username IS NULL THEN
        RETURN NEW;
    END IF;

    PERFORM crm.statistics_emit_field_event(
        'field_disruption_found',
        NEW.key,
        v_match.report_username,
        COALESCE(v_match.report_at, v_at),
        jsonb_build_object('source', 'trigger', 'via', 'tasks_insert_field_data')
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

-- Office: camera-analysis tasks only.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT;
BEGIN
    IF COALESCE(NEW.is_field_data, false) IS TRUE THEN
        RETURN NEW;
    END IF;

    IF COALESCE(NEW.is_office_task, false) IS NOT TRUE THEN
        RETURN NEW;
    END IF;

    v_login := crm.statistics_audit_login(NEW.user_created);
    PERFORM crm.statistics_emit_office_event(
        'office_camera_tasks_created',
        'task',
        NEW.key,
        v_login,
        crm.statistics_audit_at(NEW.user_created, NOW()),
        jsonb_build_object(
            'source', 'trigger',
            'task_type', NEW.type,
            'is_office_task', true
        )
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_insert ON crm.tasks;
CREATE TRIGGER trg_statistics_tasks_insert
    AFTER INSERT ON crm.tasks
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_insert();

-- Office: closed legal / illegal snapshots.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_done_legal_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM crm.statistics_emit_office_event(
        'office_closed_legal',
        'task',
        NEW.task_key,
        crm.statistics_audit_login(NEW.user_created),
        crm.statistics_audit_at(NEW.user_created, COALESCE(NEW.sent_at, NOW())),
        jsonb_build_object('source', 'trigger', 'snapshot', 'tasks_done_legal')
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_done_legal_insert ON crm.tasks_done_legal;
CREATE TRIGGER trg_statistics_tasks_done_legal_insert
    AFTER INSERT ON crm.tasks_done_legal
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_done_legal_insert();

CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_done_illegal_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM crm.statistics_emit_office_event(
        'office_closed_illegal',
        'task',
        NEW.task_key,
        crm.statistics_audit_login(NEW.user_created),
        crm.statistics_audit_at(NEW.user_created, COALESCE(NEW.sent_at, NOW())),
        jsonb_build_object('source', 'trigger', 'snapshot', 'tasks_done_illegal')
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_done_illegal_insert ON crm.tasks_done_illegal;
CREATE TRIGGER trg_statistics_tasks_done_illegal_insert
    AFTER INSERT ON crm.tasks_done_illegal
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_done_illegal_insert();

-- Field: order closed by field executor.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_area_status()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('crm.statistics_skip_area_complete', true) = 'true' THEN
        RETURN NEW;
    END IF;

    IF OLD.status IS DISTINCT FROM NEW.status
       AND OLD.status = 'wip'
       AND NEW.status = 'done'
       AND NULLIF(TRIM(NEW.executor), '') IS NOT NULL
       AND crm.statistics_resolve_role(NEW.executor) = 'field'
    THEN
        PERFORM crm.statistics_insert_row(
            NEW.executor,
            'field',
            'order',
            'field_order_closed',
            NEW.key,
            NOW(),
            jsonb_build_object(
                'source', 'trigger',
                'rayon', NEW.rayon,
                'from_status', OLD.status,
                'to_status', NEW.status
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_area_status ON crm.tasks_area;
CREATE TRIGGER trg_statistics_tasks_area_status
    AFTER UPDATE OF status ON crm.tasks_area
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_area_status();

-- Office: analise started / completed.
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_area_analise()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.analise_started_at IS NULL
       AND NEW.analise_started_at IS NOT NULL
       AND NULLIF(TRIM(NEW.analise_started_by), '') IS NOT NULL
    THEN
        PERFORM crm.statistics_emit_office_event(
            'office_analise_started',
            'order',
            NEW.key,
            NEW.analise_started_by,
            NEW.analise_started_at,
            jsonb_build_object('source', 'trigger', 'rayon', NEW.rayon)
        );
    END IF;

    IF (
        (COALESCE(OLD.analise, false) IS DISTINCT FROM TRUE AND NEW.analise IS TRUE)
        OR (OLD.analise_finished_at IS NULL AND NEW.analise_finished_at IS NOT NULL)
    )
    AND NULLIF(TRIM(NEW.analise_finished_by), '') IS NOT NULL
    THEN
        PERFORM crm.statistics_emit_office_event(
            'office_analise_completed',
            'order',
            NEW.key,
            NEW.analise_finished_by,
            COALESCE(NEW.analise_finished_at, NOW()),
            jsonb_build_object('source', 'trigger', 'rayon', NEW.rayon)
        );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_area_analise ON crm.tasks_area;
CREATE TRIGGER trg_statistics_tasks_area_analise
    AFTER UPDATE OF analise, analise_started_at, analise_started_by, analise_finished_at, analise_finished_by
    ON crm.tasks_area
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_area_analise();
