-- Order route storage for planned survey routes (OSRM-built).
CREATE TABLE IF NOT EXISTS crm.order_routes (
    order_key UUID PRIMARY KEY REFERENCES crm.tasks_area(key) ON DELETE CASCADE,
    route_geom GEOMETRY(MultiLineString, 4326),
    buffer_geom GEOMETRY(MultiPolygon, 4326),
    segments JSONB DEFAULT '[]'::jsonb,
    task_coverage_pct FLOAT,
    polygon_coverage_pct FLOAT,
    uncovered_geom GEOMETRY(Geometry, 4326),
    buffer_m FLOAT NOT NULL DEFAULT 100,
    task_count INT NOT NULL DEFAULT 0,
    total_distance_m FLOAT,
    total_duration_s FLOAT,
    built_by TEXT,
    built_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    params JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_order_routes_route_geom
    ON crm.order_routes USING GIST (route_geom)
    WHERE route_geom IS NOT NULL;

COMMENT ON TABLE crm.order_routes IS 'Planned survey routes for area orders, built via OSRM.';
