#!/usr/bin/env bash
# Обновление MONITOR Web CRM на VPS (запускать на сервере из /opt/monitor/webcrm).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .git ]]; then
  git pull
fi

ENV_FILE="$ROOT/backend/.env"
merge_env_key() {
  local key="$1"
  local value="$2"
  if [[ -f "$ENV_FILE" ]] && ! grep -q "^${key}=" "$ENV_FILE"; then
    echo "${key}=${value}" >> "$ENV_FILE"
    echo "  added ${key} to .env"
  fi
}

merge_env_key FIELD_PHOTO_STORAGE_DIR /opt/monitor/mggtfield_photo
merge_env_key FIELD_PHOTO_SFTP_REMOTE_DIR /opt/monitor/mggtfield_photo
merge_env_key OSM_TILE_URL 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
merge_env_key NOMINATIM_URL 'https://nominatim.openstreetmap.org/reverse'
merge_env_key GEOCODE_USER_AGENT '"MONITOR-WebCRM/1.0 (oati-letters)"'
merge_env_key GEOCODE_TIMEOUT_SECONDS 8.0

cd backend
source venv/bin/activate
pip install -q -r requirements.txt

echo "=== SQL migrations ==="
set -a
# shellcheck disable=SC1091
source .env
set +a
export PGPASSWORD="${DB_PASSWORD:-}"

PSQL=(psql -v ON_ERROR_STOP=1
  -h "${DB_HOST:-localhost}"
  -U "${DB_USER:-monitor}"
  -d "${DB_NAME:-monitor}")

migration_applied() {
  local base="$1"
  local result
  result=$("${PSQL[@]}" -tAc \
    "SELECT 1 FROM webcrm.schema_migrations WHERE filename = '${base}'" 2>/dev/null || true)
  [[ -n "${result// }" ]]
}

record_migration() {
  local base="$1"
  "${PSQL[@]}" -c \
    "INSERT INTO webcrm.schema_migrations (filename) VALUES ('${base}') ON CONFLICT DO NOTHING"
}

bootstrap_existing_prod() {
  local count source_col_exists
  count=$("${PSQL[@]}" -tAc "SELECT COUNT(*) FROM webcrm.schema_migrations" 2>/dev/null || echo "0")
  count="${count// /}"
  if [[ "$count" != "0" ]]; then
    return 0
  fi

  source_col_exists=$("${PSQL[@]}" -tAc \
    "SELECT 1 FROM information_schema.columns
     WHERE table_schema = 'crm' AND table_name = 'tasks' AND column_name = 'source_global_id'" \
    2>/dev/null || true)
  source_col_exists="${source_col_exists// /}"

  if [[ -z "$source_col_exists" && "${MIGRATIONS_BOOTSTRAP:-0}" != "1" ]]; then
    return 0
  fi

  echo "  bootstrap: marking existing migrations as applied (prod database detected)"
  local f base
  for f in "$ROOT"/sql/[0-9]*.sql "$ROOT"/sql/one_time/*.sql; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    record_migration "$base"
    echo "    marked $base"
  done
}

echo "  00_webcrm_schema_migrations.sql"
"${PSQL[@]}" -f "$ROOT/sql/00_webcrm_schema_migrations.sql"

bootstrap_existing_prod

for f in "$ROOT"/sql/[0-9]*.sql; do
  [[ -f "$f" ]] || continue
  base=$(basename "$f")
  if migration_applied "$base"; then
    echo "  skip $base (already applied)"
    continue
  fi
  echo "  apply $base"
  "${PSQL[@]}" -f "$f"
  record_migration "$base"
done

cd ../frontend
npm ci
npm run build
mkdir -p /var/www/monitor-webcrm
rm -rf /var/www/monitor-webcrm/*
cp -r dist/* /var/www/monitor-webcrm/

systemctl restart monitor-webcrm
echo "Deploy complete. Check backend: curl http://127.0.0.1:8080/health"
