-- WebCRM deploy migration tracking (separate from crm schema used by QGIS/MONITOR).

CREATE SCHEMA IF NOT EXISTS webcrm;

CREATE TABLE IF NOT EXISTS webcrm.schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
