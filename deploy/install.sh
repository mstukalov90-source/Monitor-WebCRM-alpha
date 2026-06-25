#!/usr/bin/env bash
# Первичная установка MONITOR Web CRM на VPS.
# Запускать на сервере из /opt/monitor/webcrm:
#   ./deploy/install.sh <SERVER_IP> [DB_PASSWORD]
set -euo pipefail

SERVER_IP="${1:-}"
DB_PASSWORD="${2:-}"

if [[ -z "$SERVER_IP" ]]; then
  echo "Usage: $0 <SERVER_IP> [DB_PASSWORD]" >&2
  exit 1
fi

if [[ -z "$DB_PASSWORD" ]]; then
  read -rsp "DB password for user monitor: " DB_PASSWORD
  echo
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DEPLOY="$ROOT/deploy"

install_packages() {
  if command -v dnf &>/dev/null; then
    dnf install -y python3 nginx nodejs postgresql
  elif command -v apt-get &>/dev/null; then
    apt-get update
    apt-get install -y python3-venv python3-pip nginx git postgresql-client
    if ! node --version 2>/dev/null | grep -qE '^v(2[0-9]|[3-9][0-9])'; then
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
      apt-get install -y nodejs
    fi
  else
    echo "Unsupported OS: need dnf or apt-get" >&2
    exit 1
  fi
}

echo "=== Installing system packages ==="
install_packages
node --version
python3 --version

echo "=== Backend venv ==="
cd "$ROOT/backend"
python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

echo "=== Production .env ==="
AUTH_KEY=$(openssl rand -hex 32)
sed -e "s|__SERVER_IP__|$SERVER_IP|g" \
    -e "s|__DB_PASSWORD__|$DB_PASSWORD|g" \
    -e "s|__AUTH_SECRET_KEY__|$AUTH_KEY|g" \
    "$DEPLOY/.env.production.template" > "$ROOT/backend/.env"
chmod 600 "$ROOT/backend/.env"

echo "=== SQL migrations ==="
export PGPASSWORD="$DB_PASSWORD"
for f in "$ROOT"/sql/0*.sql; do
  echo "  $f"
  psql -h localhost -U monitor -d monitor -f "$f" >/dev/null
done

echo "=== Frontend build ==="
cd "$ROOT/frontend"
npm ci
npm run build
mkdir -p /var/www/monitor-webcrm
rm -rf /var/www/monitor-webcrm/*
cp -r dist/* /var/www/monitor-webcrm/

echo "=== systemd + nginx ==="
NGINX_CONF=/etc/nginx/conf.d/monitor-webcrm.conf
if [[ -d /etc/nginx/sites-available ]]; then
  NGINX_CONF=/etc/nginx/sites-available/monitor-webcrm
fi
sed "s|__SERVER_IP__|$SERVER_IP|g" \
  "$DEPLOY/nginx.conf.template" > "$NGINX_CONF"

cp "$DEPLOY/monitor-webcrm.service" /etc/systemd/system/monitor-webcrm.service
chmod +x "$DEPLOY/deploy.sh"

if [[ -d /etc/nginx/sites-enabled ]]; then
  ln -sf /etc/nginx/sites-available/monitor-webcrm /etc/nginx/sites-enabled/monitor-webcrm
  rm -f /etc/nginx/sites-enabled/default
fi

systemctl daemon-reload
systemctl enable monitor-webcrm nginx
systemctl restart monitor-webcrm nginx

echo ""
echo "=== Install complete ==="
echo "  http://$SERVER_IP/health"
echo "  http://$SERVER_IP/"
