-- Statistics v2 backfill: remove legacy actions and rebuild v2 rows (idempotent).

DELETE FROM crm.statistics
WHERE action NOT IN (
    'field_camera_survey',
    'field_disruption_absent',
    'field_disruption_found',
    'field_order_closed',
    'office_analise_started',
    'office_analise_completed',
    'office_disruption_absent',
    'office_camera_tasks_created',
    'office_closed_illegal',
    'office_closed_legal'
);

-- Field: disruption absent (report + tasks_clear).
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT DISTINCT ON (c.task_key)
    u.uuid,
    r.username,
    'field',
    'task',
    'field_disruption_absent',
    c.task_key,
    COALESCE(r.created_at, crm.statistics_audit_at(c.user_created, COALESCE(c.sent_at, NOW()))),
    jsonb_build_object('source', 'backfill', 'via', 'report_and_tasks_clear')
FROM crm.tasks_clear c
JOIN mggt_field.reports r ON r.tasks_key = c.task_key
JOIN crm.users u ON u.login = r.username AND u.role = 'field'
WHERE NULLIF(TRIM(r.username), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = c.task_key
        AND s.action = 'field_disruption_absent'
  )
ORDER BY c.task_key, r.created_at DESC;

-- Field: disruption found (report + is_field_data task).
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

-- Field: camera survey (report, not clear, not field_data discovery, not in tasks_field).
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT DISTINCT ON (r.tasks_key)
    u.uuid,
    r.username,
    'field',
    'task',
    'field_camera_survey',
    r.tasks_key,
    r.created_at,
    jsonb_build_object('source', 'backfill', 'heuristic', true)
FROM mggt_field.reports r
JOIN crm.users u ON u.login = r.username AND u.role = 'field'
WHERE r.tasks_key IS NOT NULL
  AND NULLIF(TRIM(r.username), '') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM crm.tasks_clear c WHERE c.task_key = r.tasks_key)
  AND NOT EXISTS (
      SELECT 1 FROM crm.tasks t
      WHERE t.key = r.tasks_key AND t.is_field_data IS TRUE
  )
  AND NOT EXISTS (SELECT 1 FROM crm.tasks_field tf WHERE tf.task_key = r.tasks_key)
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = r.tasks_key
        AND s.action = 'field_camera_survey'
  )
ORDER BY r.tasks_key, r.created_at DESC;

-- Field: order closed.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    ta.executor,
    'field',
    'order',
    'field_order_closed',
    ta.key,
    COALESCE(
        (ta.user_last_edit[2])::timestamptz,
        ta.analise_finished_at,
        NOW()
    ),
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon, 'status', 'done')
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.executor AND u.role = 'field'
WHERE ta.status = 'done'
  AND NULLIF(TRIM(ta.executor), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order'
        AND s.object_key = ta.key
        AND s.action = 'field_order_closed'
  );

-- Office: disruption absent (tasks_clear without field report).
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    c.user_created[1],
    'office',
    'task',
    'office_disruption_absent',
    c.task_key,
    crm.statistics_audit_at(c.user_created, COALESCE(c.sent_at, NOW())),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_clear')
FROM crm.tasks_clear c
JOIN crm.users u ON u.login = c.user_created[1]
  AND u.role IN ('office', 'manager', 'admin')
WHERE c.user_created IS NOT NULL
  AND array_length(c.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1
      FROM mggt_field.reports r
      JOIN crm.users fu ON fu.login = r.username AND fu.role = 'field'
      WHERE r.tasks_key = c.task_key
        AND NULLIF(TRIM(r.username), '') IS NOT NULL
  )
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = c.task_key
        AND s.action = 'office_disruption_absent'
  );

-- Office: camera tasks created.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    t.user_created[1],
    'office',
    'task',
    'office_camera_tasks_created',
    t.key,
    crm.statistics_audit_at(t.user_created, NOW()),
    jsonb_build_object('source', 'backfill', 'is_office_task', true)
FROM crm.tasks t
JOIN crm.users u ON u.login = t.user_created[1]
  AND u.role IN ('office', 'manager', 'admin')
WHERE t.is_office_task IS TRUE
  AND t.user_created IS NOT NULL
  AND array_length(t.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = t.key
        AND s.action = 'office_camera_tasks_created'
  );

-- Office: closed legal.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    d.user_created[1],
    'office',
    'task',
    'office_closed_legal',
    d.task_key,
    crm.statistics_audit_at(d.user_created, COALESCE(d.sent_at, NOW())),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_done_legal')
FROM crm.tasks_done_legal d
JOIN crm.users u ON u.login = d.user_created[1]
  AND u.role IN ('office', 'manager', 'admin')
WHERE d.user_created IS NOT NULL
  AND array_length(d.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = d.task_key
        AND s.action = 'office_closed_legal'
  );

-- Office: closed illegal.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    d.user_created[1],
    'office',
    'task',
    'office_closed_illegal',
    d.task_key,
    crm.statistics_audit_at(d.user_created, COALESCE(d.sent_at, NOW())),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_done_illegal')
FROM crm.tasks_done_illegal d
JOIN crm.users u ON u.login = d.user_created[1]
  AND u.role IN ('office', 'manager', 'admin')
WHERE d.user_created IS NOT NULL
  AND array_length(d.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task'
        AND s.object_key = d.task_key
        AND s.action = 'office_closed_illegal'
  );

-- Office: analise started.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    ta.analise_started_by,
    'office',
    'order',
    'office_analise_started',
    ta.key,
    ta.analise_started_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.analise_started_by
  AND u.role IN ('office', 'manager', 'admin')
WHERE ta.analise_started_at IS NOT NULL
  AND NULLIF(TRIM(ta.analise_started_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order'
        AND s.object_key = ta.key
        AND s.action = 'office_analise_started'
  );

-- Office: analise completed.
INSERT INTO crm.statistics (
    user_id, user_login, user_role, object_type, action, object_key, created_at, metadata
)
SELECT
    u.uuid,
    ta.analise_finished_by,
    'office',
    'order',
    'office_analise_completed',
    ta.key,
    ta.analise_finished_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.analise_finished_by
  AND u.role IN ('office', 'manager', 'admin')
WHERE ta.analise_finished_at IS NOT NULL
  AND NULLIF(TRIM(ta.analise_finished_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order'
        AND s.object_key = ta.key
        AND s.action = 'office_analise_completed'
  );
