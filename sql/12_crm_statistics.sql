-- CRM employee action statistics (field + office).

CREATE SCHEMA IF NOT EXISTS crm;

CREATE TABLE IF NOT EXISTS crm.statistics (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID REFERENCES crm.users(uuid) ON DELETE SET NULL,
    user_login   TEXT NOT NULL,
    user_role    TEXT NOT NULL
        CHECK (user_role IN ('field', 'office')),
    object_type  TEXT NOT NULL
        CHECK (object_type IN ('task', 'order')),
    action       TEXT NOT NULL,
    object_key   UUID NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_crm_statistics_user_created
    ON crm.statistics (user_login, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crm_statistics_user_id_created
    ON crm.statistics (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_crm_statistics_type_action_created
    ON crm.statistics (object_type, action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crm_statistics_object_action
    ON crm.statistics (object_type, object_key, action);

-- Map manager/admin session logins to office role in statistics rows.
CREATE OR REPLACE FUNCTION crm.statistics_resolve_role(p_login TEXT)
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN u.role = 'field' THEN 'field'
        WHEN u.role IN ('office', 'manager', 'admin') THEN 'office'
        ELSE NULL
    END
    FROM crm.users u
    WHERE u.login = NULLIF(TRIM(p_login), '')
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION crm.statistics_insert_row(
    p_login TEXT,
    p_role TEXT,
    p_object_type TEXT,
    p_action TEXT,
    p_object_key UUID,
    p_created_at TIMESTAMPTZ DEFAULT NOW(),
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT := NULLIF(TRIM(p_login), '');
    v_role TEXT := p_role;
    v_user_id UUID;
BEGIN
    IF v_login IS NULL OR p_object_key IS NULL THEN
        RETURN;
    END IF;

    IF v_role IS NULL THEN
        v_role := crm.statistics_resolve_role(v_login);
    END IF;

    IF v_role NOT IN ('field', 'office') THEN
        RETURN;
    END IF;

    SELECT uuid INTO v_user_id
    FROM crm.users
    WHERE login = v_login
    LIMIT 1;

    IF EXISTS (
        SELECT 1
        FROM crm.statistics s
        WHERE s.object_type = p_object_type
          AND s.object_key = p_object_key
          AND s.action = p_action
    ) THEN
        RETURN;
    END IF;

    INSERT INTO crm.statistics (
        user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
    ) VALUES (
        v_user_id,
        v_login,
        v_role,
        p_object_type,
        p_action,
        p_object_key,
        COALESCE(p_created_at, NOW()),
        COALESCE(p_metadata, '{}'::jsonb)
    );
END;
$$;

-- Field mobile: task completed when removed from tasks_field (unless web CRM sets skip flag).
CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_field_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_login TEXT;
    v_created_at TIMESTAMPTZ;
BEGIN
    IF current_setting('crm.statistics_skip_field_complete', true) = 'true' THEN
        RETURN OLD;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM mggt_field.reports r WHERE r.tasks_key = OLD.task_key
    ) THEN
        RETURN OLD;
    END IF;

    SELECT r.username, r.created_at
    INTO v_login, v_created_at
    FROM mggt_field.reports r
    WHERE r.tasks_key = OLD.task_key
    ORDER BY r.created_at DESC
    LIMIT 1;

    v_login := COALESCE(NULLIF(TRIM(OLD.executor), ''), NULLIF(TRIM(v_login), ''));
    IF v_login IS NULL OR crm.statistics_resolve_role(v_login) <> 'field' THEN
        RETURN OLD;
    END IF;

    PERFORM crm.statistics_insert_row(
        v_login,
        'field',
        'task',
        'task_completed',
        OLD.task_key,
        COALESCE(v_created_at, NOW()),
        jsonb_build_object('source', 'trigger', 'snapshot_key', OLD.key::text)
    );

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_field_delete ON crm.tasks_field;
CREATE TRIGGER trg_statistics_tasks_field_delete
    AFTER DELETE ON crm.tasks_field
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_field_delete();

-- Field mobile: first report for a field-data task -> task_created.
CREATE OR REPLACE FUNCTION crm.trg_statistics_reports_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_is_field_data BOOLEAN;
BEGIN
    IF NEW.tasks_key IS NULL OR NULLIF(TRIM(NEW.username), '') IS NULL THEN
        RETURN NEW;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mggt_field.reports r
        WHERE r.tasks_key = NEW.tasks_key
          AND r.ctid <> NEW.ctid
    ) THEN
        RETURN NEW;
    END IF;

    SELECT COALESCE(t.is_field_data, false)
    INTO v_is_field_data
    FROM crm.tasks t
    WHERE t.key = NEW.tasks_key;

    IF NOT v_is_field_data THEN
        RETURN NEW;
    END IF;

    PERFORM crm.statistics_insert_row(
        NEW.username,
        'field',
        'task',
        'task_created',
        NEW.tasks_key,
        COALESCE(NEW.created_at, NOW()),
        jsonb_build_object('source', 'trigger', 'report_task', NEW.task)
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_reports_insert ON mggt_field.reports;
CREATE TRIGGER trg_statistics_reports_insert
    AFTER INSERT ON mggt_field.reports
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_reports_insert();

-- Field: order completed when field executor closes survey wip -> done via mobile.
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
       AND NULLIF(TRIM(NEW.user_last_edit[1]), '') = NULLIF(TRIM(NEW.executor), '')
       AND crm.statistics_resolve_role(NEW.executor) = 'field'
    THEN
        PERFORM crm.statistics_insert_row(
            NEW.executor,
            'field',
            'order',
            'order_completed',
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

-- Office collect: new tasks inserted via web CRM (not field-data).
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

    v_login := NULLIF(TRIM(NEW.user_created[1]), '');
    IF v_login IS NULL OR crm.statistics_resolve_role(v_login) <> 'office' THEN
        RETURN NEW;
    END IF;

    PERFORM crm.statistics_insert_row(
        v_login,
        'office',
        'task',
        'task_created',
        NEW.key,
        COALESCE((NEW.user_created[2])::timestamptz, NOW()),
        jsonb_build_object('source', 'trigger', 'task_type', NEW.type)
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_statistics_tasks_insert ON crm.tasks;
CREATE TRIGGER trg_statistics_tasks_insert
    AFTER INSERT ON crm.tasks
    FOR EACH ROW
    EXECUTE FUNCTION crm.trg_statistics_tasks_insert();
