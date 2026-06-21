-- Таблица-снимок «разрытие отсутствует» (совместимо с MONITOR_QGIS)

CREATE TABLE IF NOT EXISTS crm.tasks_clear (
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

CREATE UNIQUE INDEX IF NOT EXISTS tasks_clear_uq_task_key
    ON crm.tasks_clear (task_key);

ALTER TABLE crm.tasks_clear ADD COLUMN IF NOT EXISTS sps TEXT;
ALTER TABLE crm.tasks_clear ADD COLUMN IF NOT EXISTS kgs TEXT;
ALTER TABLE crm.tasks_clear ADD COLUMN IF NOT EXISTS station_avr TEXT;
