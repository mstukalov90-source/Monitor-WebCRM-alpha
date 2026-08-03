#!/usr/bin/env bash
# Обновление кода и БД на прод- и тест-серверах с локальной машины.
#   172.21.198.219 — прод WebCRM (нужен VPN)
#   77.222.63.161  — только тестирование
# Внешний API (monitor-crm.mggt.ru) этим скриптом не затрагивается.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_KEY="${SSH_KEY:-$ROOT/id_rsa/id_rsa}"
RSYNC_EXCLUDES=(
  --exclude backend/venv
  --exclude backend/.env
  --exclude backend/data/photo_cache
  --exclude frontend/node_modules
  --exclude frontend/dist
  --exclude .git
  --exclude tmp
  --exclude id_rsa
  --exclude .codegraph
  --exclude graphify-out
  --exclude frontend/graphify-out
)

SERVERS=(
  "77.222.63.161"   # тест
  "172.21.198.219"  # прод WebCRM
)

for host in "${SERVERS[@]}"; do
  echo "=== $host: rsync ==="
  if [[ "$host" == "77.222.63.161" && -f "$SSH_KEY" ]]; then
    rsync -avz "${RSYNC_EXCLUDES[@]}" -e "ssh -i $SSH_KEY" "$ROOT/" "root@$host:/opt/monitor/webcrm/"
  else
    rsync -avz "${RSYNC_EXCLUDES[@]}" "$ROOT/" "root@$host:/opt/monitor/webcrm/"
  fi

  echo "=== $host: deploy ==="
  if [[ "$host" == "77.222.63.161" && -f "$SSH_KEY" ]]; then
    ssh -i "$SSH_KEY" "root@$host" 'cd /opt/monitor/webcrm && chmod +x deploy/deploy.sh && ./deploy/deploy.sh'
  else
    ssh "root@$host" 'cd /opt/monitor/webcrm && chmod +x deploy/deploy.sh && ./deploy/deploy.sh'
  fi

  echo "=== $host: health (WebCRM :8080) ==="
  if [[ "$host" == "77.222.63.161" && -f "$SSH_KEY" ]]; then
    ssh -i "$SSH_KEY" "root@$host" "curl -s http://127.0.0.1:8080/health"
  else
    # На проде /health на :80 — MONITOR API, не WebCRM
    ssh "root@$host" "curl -s http://127.0.0.1:8080/health"
  fi
  echo ""
done

echo "Done."
