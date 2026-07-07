#!/usr/bin/env bash
# Nightly link health check after data_mos ETL.
# Usage: ./scripts/link_health_check.sh [PGHOST] [PGDATABASE] [PGUSER]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGHOST="${1:-${PGHOST:-77.222.63.161}}"
PGDATABASE="${2:-${PGDATABASE:-monitor}}"
PGUSER="${3:-${PGUSER:-monitor}}"

export PGHOST PGDATABASE PGUSER

echo "=== Link health check $(date -Iseconds) ==="
echo "Host: $PGHOST DB: $PGDATABASE User: $PGUSER"

ISSUES=$(psql -v ON_ERROR_STOP=1 -t -A -c "
SELECT COUNT(*) FROM (
    SELECT ct.key
    FROM crm.tasks ct
    WHERE (ct.oati_id IS NOT NULL OR ct.earthwork_id IS NOT NULL
           OR ct.localwork_id IS NOT NULL OR ct.avr_mos_id IS NOT NULL)
      AND ct.is_field_data IS NOT TRUE
      AND ct.is_office_task IS NOT TRUE
      AND (
          ct.oati_id ~ '^(point|line|polygon):'
          OR ct.earthwork_id ~ '^(point|line|polygon):'
          OR ct.localwork_id ~ '^(point|line|polygon):'
          OR ct.avr_mos_id ~ '^(point|line|polygon):'
      )
      AND NOT EXISTS (
          SELECT 1 FROM data_mos.items_2855_points t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_2855_lines t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_2855_polygons t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62501_points t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62501_lines t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62501_polygons t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62441_points t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62441_lines t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62441_polygons t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62461_points t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62461_lines t WHERE t.task_key = ct.key
          UNION ALL SELECT 1 FROM data_mos.items_62461_polygons t WHERE t.task_key = ct.key
      )
) orphan_tasks;
")

LINKED=$(psql -v ON_ERROR_STOP=1 -t -A -c "
SELECT COUNT(*) FROM (
    SELECT task_key FROM data_mos.items_2855_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_2855_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_2855_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62501_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62501_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62501_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62441_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62441_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62441_polygons WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62461_points WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62461_lines WHERE task_key IS NOT NULL
    UNION ALL SELECT task_key FROM data_mos.items_62461_polygons WHERE task_key IS NOT NULL
) s;
")

echo "Linked items rows: $LINKED"
echo "Orphan tasks (no items link): $ISSUES"

if [ "$ISSUES" -gt 0 ]; then
    echo "WARN: orphan tasks detected — run sql/25_link_health_report.sql for details"
    exit 1
fi

echo "OK: link health check passed"
exit 0
