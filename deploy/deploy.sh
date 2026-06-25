#!/usr/bin/env bash
# Обновление MONITOR Web CRM на VPS (запускать на сервере из /opt/monitor/webcrm).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .git ]]; then
  git pull
fi

cd backend
source venv/bin/activate
pip install -q -r requirements.txt

cd ../frontend
npm ci
npm run build
mkdir -p /var/www/monitor-webcrm
rm -rf /var/www/monitor-webcrm/*
cp -r dist/* /var/www/monitor-webcrm/

systemctl restart monitor-webcrm
echo "Deploy complete. Check backend: curl http://127.0.0.1:8080/health"
