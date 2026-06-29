-- Маркер задач «Задачи из камерального анализа» (office-точки на карте)
ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS is_office_task BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS is_office_task BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS is_office_task BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS is_office_task BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crm.tasks_clear ADD COLUMN IF NOT EXISTS is_office_task BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS crm.office_task_points (
    task_key UUID PRIMARY KEY REFERENCES crm.tasks(key) ON DELETE CASCADE,
    point GEOMETRY(Point, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_office_task_points_geom
    ON crm.office_task_points USING GIST (point);
