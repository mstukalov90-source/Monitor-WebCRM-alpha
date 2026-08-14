-- Backfill field_order_closed for orders closed 2026-08-13 (MSK).
-- Mobile sets date_survey on close and often does not update user_last_edit,
-- so yesterday's closures are identified by status=done AND date_survey.

DO $$
DECLARE
    r RECORD;
    v_closed_at TIMESTAMPTZ;
BEGIN
    FOR r IN
        SELECT
            ta.key,
            ta.executor,
            ta.rayon,
            ta.date_survey
        FROM crm.tasks_area ta
        WHERE ta.status = 'done'
          AND ta.date_survey = DATE '2026-08-13'
          AND NULLIF(TRIM(ta.executor), '') IS NOT NULL
          AND crm.statistics_resolve_role(ta.executor) = 'field'
    LOOP
        v_closed_at := (r.date_survey::timestamp + TIME '12:00') AT TIME ZONE 'Europe/Moscow';
        PERFORM crm.statistics_insert_row(
            r.executor,
            'field',
            'order',
            'field_order_closed',
            r.key,
            v_closed_at,
            jsonb_build_object(
                'source', 'backfill',
                'rayon', r.rayon,
                'reason', 'closed_to_done_date_survey_2026-08-13'
            )
        );
    END LOOP;
END
$$;
