#!/usr/bin/env bash
# Run a one-time SQL migration with safety checks.
#
# Usage:
#   ./scripts/run_one_time_migration.sh sql/one_time/28_cleanup_link_orphan_tasks.sql
#   ALLOW_DESTRUCTIVE_MIGRATION=1 ./scripts/run_one_time_migration.sh sql/one_time/28_cleanup_link_orphan_tasks.sql
#
# Destructive migrations (DELETE crm.tasks) require ALLOW_DESTRUCTIVE_MIGRATION=1
# when the dry-run count exceeds 100 rows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <sql-file> [sql-file ...]" >&2
  echo "Set ALLOW_DESTRUCTIVE_MIGRATION=1 to allow mass DELETE (>100 rows)." >&2
  exit 1
fi

ENV_FILE="$ROOT/backend/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi
export PGPASSWORD="${DB_PASSWORD:-}"

PSQL=(psql -v ON_ERROR_STOP=1
  -h "${DB_HOST:-localhost}"
  -U "${DB_USER:-monitor}"
  -d "${DB_NAME:-monitor}")

DESTRUCTIVE_MIGRATIONS=(
  17_tasks_business_id_unique.sql
  18_earthwork_restore_point_tasks.sql
  20_oati_scoped_geometry_tasks.sql
  21_localwork_avr_scoped_geometry_tasks.sql
  28_cleanup_link_orphan_tasks.sql
)

is_destructive() {
  local base="$1"
  local name
  for name in "${DESTRUCTIVE_MIGRATIONS[@]}"; do
    [[ "$base" == "$name" ]] && return 0
  done
  return 1
}

dry_run_28_count() {
  "${PSQL[@]}" -tAc "
SELECT COUNT(*) FROM (
    SELECT ct.key
    FROM crm.tasks ct
    WHERE ct.is_field_data IS NOT TRUE
      AND ct.is_office_task IS NOT TRUE
      AND NOT ('etl' = ANY(COALESCE(ct.user_created, ARRAY[]::text[])))
      AND (
          ct.oati_id IS NOT NULL OR ct.earthwork_id IS NOT NULL
          OR ct.localwork_id IS NOT NULL OR ct.avr_mos_id IS NOT NULL
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
) orphans;
" 2>/dev/null || echo "0"
}

echo "=== One-time migration runner ==="
"${PSQL[@]}" -f "$ROOT/sql/00_webcrm_schema_migrations.sql" >/dev/null

for sql_file in "$@"; do
  if [[ ! -f "$sql_file" ]]; then
    if [[ -f "$ROOT/$sql_file" ]]; then
      sql_file="$ROOT/$sql_file"
    else
      echo "File not found: $sql_file" >&2
      exit 1
    fi
  fi

  base=$(basename "$sql_file")
  already=$("${PSQL[@]}" -tAc \
    "SELECT 1 FROM webcrm.schema_migrations WHERE filename = '${base}'" 2>/dev/null || true)
  if [[ -n "${already// }" ]]; then
    echo "skip $base (already applied)"
    continue
  fi

  if is_destructive "$base" && [[ "${ALLOW_DESTRUCTIVE_MIGRATION:-0}" != "1" ]]; then
    if [[ "$base" == "28_cleanup_link_orphan_tasks.sql" ]]; then
      count=$(dry_run_28_count)
      count="${count// /}"
      echo "dry-run $base: orphan count (non-ETL) = $count"
      if [[ "$count" -gt 100 ]]; then
        echo "ABORT: $count rows would be deleted (>100). Set ALLOW_DESTRUCTIVE_MIGRATION=1 to proceed." >&2
        exit 1
      fi
    else
      echo "ABORT: $base is destructive. Set ALLOW_DESTRUCTIVE_MIGRATION=1 to proceed." >&2
      exit 1
    fi
  fi

  echo "apply $base"
  allow_flag="${ALLOW_DESTRUCTIVE_MIGRATION:-0}"
  "${PSQL[@]}" -v "webcrm.allow_destructive=${allow_flag}" -f "$sql_file"
  "${PSQL[@]}" -c \
    "INSERT INTO webcrm.schema_migrations (filename) VALUES ('${base}') ON CONFLICT DO NOTHING"
  echo "recorded $base"
done

echo "Done."
