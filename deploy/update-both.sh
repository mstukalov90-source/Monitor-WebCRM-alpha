#!/usr/bin/env bash
# Обновление кода и БД на обоих VPS с локальной машины.
# Требуется VPN для доступа к 172.21.198.219.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_KEY="${SSH_KEY:-$ROOT/id_rsa/id_rsa}"
RSYNC_EXCLUDES=(
  --exclude backend/venv
  --exclude backend/data/photo_cache
  --exclude frontend/node_modules
  --exclude frontend/dist
  --exclude .git
  --exclude tmp
  --exclude id_rsa
  --exclude .codegraph
)

SERVERS=(
  "77.222.63.161"
  "172.21.198.219"
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

  echo "=== $host: health ==="
  if [[ "$host" == "77.222.63.161" && -f "$SSH_KEY" ]]; then
    ssh -i "$SSH_KEY" "root@$host" "curl -s http://$host/health"
  else
    ssh "root@$host" "curl -s http://$host/health"
  fi
  echo ""
done

echo "Done."
