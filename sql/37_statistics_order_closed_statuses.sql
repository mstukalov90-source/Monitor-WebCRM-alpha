-- Field order close: mobile now finishes survey from wip_field or in_pause
-- (WebCRM complete-survey still uses wip -> done). Idempotent backfill of
-- done orders since 2026-08-13 MSK that were missed by the old trigger.

CREATE OR REPLACE FUNCTION crm.trg_statistics_tasks_area_status()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('crm.statistics_skip_area_complete', true) = 'true' THEN
        RETURN NEW;
    END IF;

    IF OLD.status IS DISTINCT FROM NEW.status
       AND OLD.status IN ('wip', 'wip_field', 'in_pause')
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

DO $$
DECLARE
    r RECORD;
    v_closed_at TIMESTAMPTZ;
    v_edit_date DATE;
    v_today DATE := (NOW() AT TIME ZONE 'Europe/Moscow')::date;
    v_from DATE := DATE '2026-08-13';
BEGIN
    FOR r IN
        SELECT
            ta.key,
            ta.executor,
            ta.rayon,
            ta.user_last_edit
        FROM crm.tasks_area ta
        WHERE ta.status = 'done'
          AND NULLIF(TRIM(ta.executor), '') IS NOT NULL
          AND crm.statistics_resolve_role(ta.executor) = 'field'
    LOOP
        BEGIN
            v_closed_at := NULLIF(TRIM(r.user_last_edit[2]), '')::timestamptz;
        EXCEPTION WHEN OTHERS THEN
            v_closed_at := NULL;
        END;

        v_edit_date := (v_closed_at AT TIME ZONE 'Europe/Moscow')::date;

        -- date_survey is a planned survey date, not close time — do not use it.
        IF v_edit_date IS NULL OR v_edit_date < v_from OR v_edit_date > v_today THEN
            CONTINUE;
        END IF;

        PERFORM crm.statistics_insert_row(
            r.executor,
            'field',
            'order',
            'field_order_closed',
            r.key,
            COALESCE(v_closed_at, NOW()),
            jsonb_build_object(
                'source', 'backfill',
                'rayon', r.rayon,
                'reason', 'closed_to_done_from_2026-08-13'
            )
        );
    END LOOP;
END
$$;
