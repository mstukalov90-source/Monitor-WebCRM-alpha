#!/usr/bin/env bash
# Deploy stable links: MONITOR sql/27 → WebCRM sql/23-26 → backfill.
# Usage: DEPLOY_HOST=77.222.63.161 ./scripts/deploy_stable_links.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONITOR_ROOT="${MONITOR_ROOT:-$(dirname "$ROOT")/MONITOR}"
DEPLOY_HOST="${DEPLOY_HOST:-77.222.63.161}"
PGDATABASE="${PGDATABASE:-monitor}"
PGUSER="${PGUSER:-monitor}"

export PGHOST="$DEPLOY_HOST" PGDATABASE PGUSER

echo "=== Deploy stable links to $DEPLOY_HOST ==="

run_sql() {
    local file="$1"
    echo ">> $file"
    psql -v ON_ERROR_STOP=1 -f "$file"
}

echo "--- Step 1: MONITOR sql/27 (task_key on items_*) ---"
run_sql "$MONITOR_ROOT/sql/27_data_mos_items_task_key.sql"

echo "--- Step 2: WebCRM sql/23-26 (anchors, field geom) ---"
run_sql "$ROOT/sql/23_crm_tasks_source_anchor.sql"
run_sql "$ROOT/sql/26_tasks_field_geom.sql"

echo "--- Step 3: Backfill (sql/24) ---"
run_sql "$ROOT/sql/24_backfill_items_task_key.sql"

echo "--- Step 4: Health report ---"
psql -f "$ROOT/sql/25_link_health_report.sql" || true

echo "--- Step 5: link_health_check ---"
"$ROOT/scripts/link_health_check.sh" "$DEPLOY_HOST" "$PGDATABASE" "$PGUSER" || true

echo "=== SQL deploy complete ==="
echo "Deploy application code separately:"
echo "  1. MONITOR collector (merge-load, geom_split)"
echo "  2. WebCRM backend"
echo "  3. MONITOR_QGIS plugin"
