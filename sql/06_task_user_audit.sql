-- User audit columns for CRM task tables.
-- Format: user_created and user_last_edit are TEXT[] = [login, ISO-8601 UTC timestamp].

DO $$
DECLARE
    tbl TEXT;
    col TEXT;
    col_type TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'tasks',
        'tasks_field',
        'tasks_done_legal',
        'tasks_done_illegal',
        'tasks_clear',
        'tasks_area'
    ]
    LOOP
        FOREACH col IN ARRAY ARRAY['user_created', 'user_last_edit']
        LOOP
            SELECT data_type INTO col_type
            FROM information_schema.columns
            WHERE table_schema = 'crm'
              AND table_name = tbl
              AND column_name = col;

            IF col_type IS NULL THEN
                EXECUTE format(
                    'ALTER TABLE crm.%I ADD COLUMN %I TEXT[]',
                    tbl, col
                );
            ELSIF col_type = 'text' THEN
                EXECUTE format(
                    'ALTER TABLE crm.%I ALTER COLUMN %I TYPE TEXT[] '
                    'USING CASE WHEN %I IS NULL THEN NULL::text[] '
                    'ELSE ARRAY[%I::text, (now() AT TIME ZONE ''utc'')::text] END',
                    tbl, col, col, col
                );
            END IF;
        END LOOP;
    END LOOP;
END $$;
