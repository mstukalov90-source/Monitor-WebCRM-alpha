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

cd backend
source venv/bin/activate
pip install -q -r requirements.txt

echo "=== SQL migrations ==="
set -a
# shellcheck disable=SC1091
source .env
set +a
export PGPASSWORD="${DB_PASSWORD:-}"
for f in "$ROOT"/sql/[0-9]*.sql; do
  echo "  $(basename "$f")"
  psql -h "${DB_HOST:-localhost}" -U "${DB_USER:-monitor}" -d "${DB_NAME:-monitor}" -f "$f" >/dev/null
done

cd ../frontend
npm ci
npm run build
mkdir -p /var/www/monitor-webcrm
rm -rf /var/www/monitor-webcrm/*
cp -r dist/* /var/www/monitor-webcrm/

systemctl restart monitor-webcrm
echo "Deploy complete. Check backend: curl http://127.0.0.1:8080/health"
