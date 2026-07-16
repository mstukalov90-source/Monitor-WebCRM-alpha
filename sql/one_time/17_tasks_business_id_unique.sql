-- Deduplicate crm.tasks by business-id columns and enforce uniqueness (QGIS + WebCRM).
-- Run once on production before deploying the fixed WebCRM backend.
-- Run once: ALLOW_DESTRUCTIVE_MIGRATION=1 ./scripts/run_one_time_migration.sh sql/one_time/17_tasks_business_id_unique.sql

BEGIN;

-- 1. Normalize whitespace in business-id columns
UPDATE crm.tasks SET photo_uuid = NULLIF(TRIM(photo_uuid), '') WHERE photo_uuid IS NOT NULL;
UPDATE crm.tasks SET photo_lens = NULLIF(TRIM(photo_lens), '') WHERE photo_lens IS NOT NULL;
UPDATE crm.tasks SET ogh_id = NULLIF(TRIM(ogh_id), '') WHERE ogh_id IS NOT NULL;
UPDATE crm.tasks SET oati_id = NULLIF(TRIM(oati_id), '') WHERE oati_id IS NOT NULL;
UPDATE crm.tasks SET earthwork_id = NULLIF(TRIM(earthwork_id), '') WHERE earthwork_id IS NOT NULL;
UPDATE crm.tasks SET localwork_id = NULLIF(TRIM(localwork_id), '') WHERE localwork_id IS NOT NULL;
UPDATE crm.tasks SET avr_mos_id = NULLIF(TRIM(avr_mos_id), '') WHERE avr_mos_id IS NOT NULL;

-- 2. Merge duplicate tasks (keep row with snapshot/report, else oldest key)
DO $$
DECLARE
    col text;
    cols text[] := ARRAY[
        'photo_uuid', 'photo_lens', 'ogh_id', 'oati_id',
        'earthwork_id', 'localwork_id', 'avr_mos_id'
    ];
    val text;
    canonical uuid;
    dup uuid;
BEGIN
    FOREACH col IN ARRAY cols LOOP
        FOR val IN
            EXECUTE format(
                'SELECT %1$I FROM crm.tasks WHERE %1$I IS NOT NULL '
                'GROUP BY %1$I HAVING COUNT(*) > 1',
                col
            )
        LOOP
            EXECUTE format(
                'SELECT key FROM crm.tasks t WHERE t.%1$I = $1 '
                'ORDER BY '
                'EXISTS(SELECT 1 FROM crm.tasks_field f WHERE f.task_key = t.key) DESC, '
                'EXISTS(SELECT 1 FROM crm.tasks_done_legal d WHERE d.task_key = t.key) DESC, '
                'EXISTS(SELECT 1 FROM crm.tasks_done_illegal d WHERE d.task_key = t.key) DESC, '
                'EXISTS(SELECT 1 FROM crm.tasks_clear c WHERE c.task_key = t.key) DESC, '
                'EXISTS(SELECT 1 FROM crm.office_task_points p WHERE p.task_key = t.key) DESC, '
                'EXISTS(SELECT 1 FROM mggt_field.reports r WHERE r.tasks_key = t.key) DESC, '
                't.key ASC '
                'LIMIT 1',
                col
            )
            INTO canonical
            USING val;

            FOR dup IN
                EXECUTE format(
                    'SELECT key FROM crm.tasks WHERE %1$I = $1 AND key <> $2',
                    col
                )
                USING val, canonical
            LOOP
                UPDATE mggt_field.reports
                SET tasks_key = canonical
                WHERE tasks_key = dup
                  AND NOT EXISTS (
                      SELECT 1 FROM mggt_field.reports r2
                      WHERE r2.tasks_key = canonical
                  );
                DELETE FROM mggt_field.reports
                WHERE tasks_key = dup;

                DELETE FROM crm.tasks_field
                WHERE task_key = dup
                  AND EXISTS (
                      SELECT 1 FROM crm.tasks_field f2
                      WHERE f2.task_key = canonical
                  );
                UPDATE crm.tasks_field SET task_key = canonical WHERE task_key = dup;

                DELETE FROM crm.tasks_done_legal
                WHERE task_key = dup
                  AND EXISTS (
                      SELECT 1 FROM crm.tasks_done_legal d2
                      WHERE d2.task_key = canonical
                  );
                UPDATE crm.tasks_done_legal SET task_key = canonical WHERE task_key = dup;

                DELETE FROM crm.tasks_done_illegal
                WHERE task_key = dup
                  AND EXISTS (
                      SELECT 1 FROM crm.tasks_done_illegal d2
                      WHERE d2.task_key = canonical
                  );
                UPDATE crm.tasks_done_illegal SET task_key = canonical WHERE task_key = dup;

                DELETE FROM crm.tasks_clear
                WHERE task_key = dup
                  AND EXISTS (
                      SELECT 1 FROM crm.tasks_clear c2
                      WHERE c2.task_key = canonical
                  );
                UPDATE crm.tasks_clear SET task_key = canonical WHERE task_key = dup;

                DELETE FROM crm.office_task_points
                WHERE task_key = dup
                  AND EXISTS (
                      SELECT 1 FROM crm.office_task_points p2
                      WHERE p2.task_key = canonical
                  );
                UPDATE crm.office_task_points SET task_key = canonical WHERE task_key = dup;

                DELETE FROM crm.tasks WHERE key = dup;
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

-- 3. Unique indexes (shared contract for QGIS + WebCRM)
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_photo_uuid
    ON crm.tasks (photo_uuid) WHERE photo_uuid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_photo_lens
    ON crm.tasks (photo_lens) WHERE photo_lens IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_ogh_id
    ON crm.tasks (ogh_id) WHERE ogh_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_oati_id
    ON crm.tasks (oati_id) WHERE oati_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_earthwork_id
    ON crm.tasks (earthwork_id) WHERE earthwork_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_localwork_id
    ON crm.tasks (localwork_id) WHERE localwork_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_uq_avr_mos_id
    ON crm.tasks (avr_mos_id) WHERE avr_mos_id IS NOT NULL;

COMMIT;
