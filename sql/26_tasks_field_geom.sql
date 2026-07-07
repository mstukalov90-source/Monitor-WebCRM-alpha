-- Snapshot geometry on field tasks (insurance when items lookup fails after ETL).
ALTER TABLE crm.tasks_field
    ADD COLUMN IF NOT EXISTS geom GEOMETRY(Geometry, 4326);

CREATE INDEX IF NOT EXISTS tasks_field_geom_gix
    ON crm.tasks_field USING GIST (geom)
    WHERE geom IS NOT NULL;
