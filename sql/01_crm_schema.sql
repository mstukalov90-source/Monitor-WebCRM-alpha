-- CRM schema (compatible with MONITOR_QGIS plugin)

CREATE SCHEMA IF NOT EXISTS crm;

CREATE TABLE IF NOT EXISTS crm.tasks (
    key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL,
    photo_uuid TEXT,
    photo_lens TEXT,
    ogh_id TEXT,
    oati_id TEXT,
    earthwork_id TEXT,
    localwork_id TEXT,
    avr_mos_id TEXT,
    sps TEXT,
    kgs TEXT,
    station_avr TEXT
);

ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS sps TEXT;
ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS kgs TEXT;
ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS station_avr TEXT;
ALTER TABLE crm.tasks ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;

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

CREATE TABLE IF NOT EXISTS crm.tasks_field (
    key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_key UUID NOT NULL REFERENCES crm.tasks(key),
    type TEXT NOT NULL,
    photo_uuid TEXT,
    photo_lens TEXT,
    ogh_id TEXT,
    oati_id TEXT,
    earthwork_id TEXT,
    localwork_id TEXT,
    avr_mos_id TEXT,
    sps TEXT,
    kgs TEXT,
    station_avr TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS tasks_field_uq_task_key
    ON crm.tasks_field (task_key);

CREATE TABLE IF NOT EXISTS crm.tasks_done_legal (
    key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_key UUID NOT NULL REFERENCES crm.tasks(key),
    type TEXT NOT NULL,
    photo_uuid TEXT,
    photo_lens TEXT,
    ogh_id TEXT,
    oati_id TEXT,
    earthwork_id TEXT,
    localwork_id TEXT,
    avr_mos_id TEXT,
    sps TEXT,
    kgs TEXT,
    station_avr TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS tasks_done_legal_uq_task_key
    ON crm.tasks_done_legal (task_key);

CREATE TABLE IF NOT EXISTS crm.tasks_done_illegal (
    key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_key UUID NOT NULL REFERENCES crm.tasks(key),
    type TEXT NOT NULL,
    photo_uuid TEXT,
    photo_lens TEXT,
    ogh_id TEXT,
    oati_id TEXT,
    earthwork_id TEXT,
    localwork_id TEXT,
    avr_mos_id TEXT,
    sps TEXT,
    kgs TEXT,
    station_avr TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS tasks_done_illegal_uq_task_key
    ON crm.tasks_done_illegal (task_key);

CREATE TABLE IF NOT EXISTS crm.tasks_area (
    key         UUID PRIMARY KEY,
    fid         BIGINT,
    gid         BIGINT,
    rayon       TEXT,
    okrug       TEXT,
    okrug_shor  TEXT,
    area        DOUBLE PRECISION,
    status      TEXT,
    date_survey DATE,
    geom        GEOMETRY(Geometry, 4326),
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_tasks_area_geom
    ON crm.tasks_area USING GIST (geom);

ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS sps TEXT;
ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS kgs TEXT;
ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS station_avr TEXT;

ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS sps TEXT;
ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS kgs TEXT;
ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS station_avr TEXT;

ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS sps TEXT;
ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS kgs TEXT;
ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS station_avr TEXT;

ALTER TABLE crm.tasks_field ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
ALTER TABLE crm.tasks_done_legal ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
ALTER TABLE crm.tasks_done_illegal ADD COLUMN IF NOT EXISTS field_observed BOOLEAN;
