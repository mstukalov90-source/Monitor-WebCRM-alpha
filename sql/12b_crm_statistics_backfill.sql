-- One-time backfill of crm.statistics from existing CRM data.
-- Idempotent: skips rows that already exist for (object_type, object_key, action).

-- Field: task_created
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT DISTINCT ON (t.key)
    u.uuid,
    COALESCE(NULLIF(TRIM(r.username), ''), NULLIF(TRIM(t.user_created[1]), '')),
    'field',
    'task',
    'task_created',
    t.key,
    COALESCE(r.created_at, (t.user_created[2])::timestamptz, NOW()),
    jsonb_build_object('source', 'backfill', 'is_field_data', true)
FROM crm.tasks t
JOIN mggt_field.reports r ON r.tasks_key = t.key
LEFT JOIN crm.users u ON u.login = r.username AND u.role = 'field'
WHERE t.is_field_data IS TRUE
  AND NULLIF(TRIM(r.username), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task' AND s.action = 'task_created' AND s.object_key = t.key
  )
ORDER BY t.key, r.created_at ASC;

-- Field: task_completed (heuristic — no DELETE audit for tasks_field)
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT DISTINCT ON (t.key)
    u.uuid,
    COALESCE(NULLIF(TRIM(r.username), ''), NULLIF(TRIM(t.user_last_edit[1]), '')),
    'field',
    'task',
    'task_completed',
    t.key,
    COALESCE(r.created_at, (t.user_last_edit[2])::timestamptz, NOW()),
    jsonb_build_object('source', 'backfill', 'heuristic', true)
FROM crm.tasks t
JOIN mggt_field.reports r ON r.tasks_key = t.key
JOIN crm.users u ON u.login = COALESCE(NULLIF(TRIM(r.username), ''), NULLIF(TRIM(t.user_last_edit[1]), ''))
WHERE u.role = 'field'
  AND NOT EXISTS (SELECT 1 FROM crm.tasks_field tf WHERE tf.task_key = t.key)
  AND (
      t.field_observed IS TRUE
      OR EXISTS (SELECT 1 FROM crm.tasks_done_legal d WHERE d.task_key = t.key)
      OR EXISTS (SELECT 1 FROM crm.tasks_done_illegal d WHERE d.task_key = t.key)
  )
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task' AND s.action = 'task_completed' AND s.object_key = t.key
  )
ORDER BY t.key, r.created_at DESC;

-- Field: order_completed
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    ta.executor,
    'field',
    'order',
    'order_completed',
    ta.key,
    (ta.user_last_edit[2])::timestamptz,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon, 'status', 'done')
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.executor AND u.role = 'field'
WHERE ta.status = 'done'
  AND ta.executor IS NOT NULL
  AND ta.user_last_edit IS NOT NULL
  AND array_length(ta.user_last_edit, 1) >= 2
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order' AND s.action = 'order_completed' AND s.object_key = ta.key
  );

-- Office: task_sent_to_field
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    tf.user_created[1],
    'office',
    'task',
    'task_sent_to_field',
    tf.task_key,
    COALESCE((tf.user_created[2])::timestamptz, tf.sent_at, NOW()),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_field')
FROM crm.tasks_field tf
JOIN crm.users u ON u.login = tf.user_created[1] AND u.role IN ('office', 'manager', 'admin')
WHERE tf.user_created IS NOT NULL
  AND array_length(tf.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task' AND s.action = 'task_sent_to_field' AND s.object_key = tf.task_key
  );

-- Office: task_closed_legal
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    d.user_created[1],
    'office',
    'task',
    'task_closed_legal',
    d.task_key,
    COALESCE((d.user_created[2])::timestamptz, d.sent_at, NOW()),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_done_legal')
FROM crm.tasks_done_legal d
JOIN crm.users u ON u.login = d.user_created[1] AND u.role IN ('office', 'manager', 'admin')
WHERE d.user_created IS NOT NULL
  AND array_length(d.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task' AND s.action = 'task_closed_legal' AND s.object_key = d.task_key
  );

-- Office: task_closed_illegal
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    d.user_created[1],
    'office',
    'task',
    'task_closed_illegal',
    d.task_key,
    COALESCE((d.user_created[2])::timestamptz, d.sent_at, NOW()),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_done_illegal')
FROM crm.tasks_done_illegal d
JOIN crm.users u ON u.login = d.user_created[1] AND u.role IN ('office', 'manager', 'admin')
WHERE d.user_created IS NOT NULL
  AND array_length(d.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task' AND s.action = 'task_closed_illegal' AND s.object_key = d.task_key
  );

-- Office: task_marked_clear
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    c.user_created[1],
    'office',
    'task',
    'task_marked_clear',
    c.task_key,
    COALESCE((c.user_created[2])::timestamptz, c.sent_at, NOW()),
    jsonb_build_object('source', 'backfill', 'snapshot', 'tasks_clear')
FROM crm.tasks_clear c
JOIN crm.users u ON u.login = c.user_created[1] AND u.role IN ('office', 'manager', 'admin')
WHERE c.user_created IS NOT NULL
  AND array_length(c.user_created, 1) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'task' AND s.action = 'task_marked_clear' AND s.object_key = c.task_key
  );

-- Office: order_analise_started
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    ta.analise_started_by,
    'office',
    'order',
    'order_analise_started',
    ta.key,
    ta.analise_started_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.analise_started_by AND u.role IN ('office', 'manager', 'admin')
WHERE ta.analise_started_at IS NOT NULL
  AND NULLIF(TRIM(ta.analise_started_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order' AND s.action = 'order_analise_started' AND s.object_key = ta.key
  );

-- Office: order_analise_paused
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    ta.analise_paused_by,
    'office',
    'order',
    'order_analise_paused',
    ta.key,
    ta.analise_paused_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.analise_paused_by AND u.role IN ('office', 'manager', 'admin')
WHERE ta.analise_paused_at IS NOT NULL
  AND NULLIF(TRIM(ta.analise_paused_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order' AND s.action = 'order_analise_paused' AND s.object_key = ta.key
  );

-- Office: order_analise_completed
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    ta.analise_finished_by,
    'office',
    'order',
    'order_analise_completed',
    ta.key,
    ta.analise_finished_at,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon)
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.analise_finished_by AND u.role IN ('office', 'manager', 'admin')
WHERE ta.analise_finished_at IS NOT NULL
  AND NULLIF(TRIM(ta.analise_finished_by), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order' AND s.action = 'order_analise_completed' AND s.object_key = ta.key
  );

-- Office: order_completed_survey (done status, office user in audit, field executor excluded above)
INSERT INTO crm.statistics (user_id, user_login, user_role, object_type, action, object_key, created_at, metadata)
SELECT
    u.uuid,
    ta.user_last_edit[1],
    'office',
    'order',
    'order_completed_survey',
    ta.key,
    (ta.user_last_edit[2])::timestamptz,
    jsonb_build_object('source', 'backfill', 'rayon', ta.rayon, 'status', 'done')
FROM crm.tasks_area ta
JOIN crm.users u ON u.login = ta.user_last_edit[1] AND u.role IN ('office', 'manager', 'admin')
WHERE ta.status = 'done'
  AND ta.user_last_edit IS NOT NULL
  AND array_length(ta.user_last_edit, 1) >= 2
  AND NOT EXISTS (
      SELECT 1 FROM crm.statistics s
      WHERE s.object_type = 'order'
        AND s.action IN ('order_completed', 'order_completed_survey')
        AND s.object_key = ta.key
  );
