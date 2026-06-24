# Деплой MONITOR Web CRM на VPS

Продакшен: **http://77.222.63.161**

Приложение разворачивается на том же сервере, где уже работают PostgreSQL/PostGIS и каталог фотографий. Локальная разработка использует SSH-туннель и SFTP — на VPS эти обходные пути не нужны.

## Архитектура

```
Браузер
   │
   ▼
nginx :80  ── GET /          ──► /var/www/monitor-webcrm/  (статика Vite)
           ── /api/*, /health ──► uvicorn 127.0.0.1:8080   (FastAPI)
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
              PostgreSQL          /opt/monitor/         shared/
              localhost:5432      downloaded_photo      layers_config.json
              (Docker)            (334+ файлов)
```

| Компонент | Путь / адрес | Примечание |
|-----------|--------------|------------|
| Код приложения | `/opt/monitor/webcrm/` | git clone или rsync |
| Backend API | `127.0.0.1:8080` | systemd `monitor-webcrm` |
| Frontend | `/var/www/monitor-webcrm/` | `npm run build` → nginx |
| БД | `localhost:5432`, база `monitor` | контейнер `monitor-db` (PostGIS 16) |
| Фото | `/opt/monitor/downloaded_photo` | метаданные в `genplan.photo_meta` |

Фронтенд обращается к API по **относительным URL** (`/api/...`). Nginx обязателен — отдельный `VITE_API_URL` не нужен.

## Требования к серверу

- Ubuntu 24.04 (или аналог)
- Python 3.12+
- **Node.js 20+** (Vite 8 не собирается на Node 18 из репозитория Ubuntu)
- nginx, git, postgresql-client
- PostgreSQL + PostGIS с базой `monitor` (уже развёрнуты)
- Каталог `/opt/monitor/downloaded_photo` с правами на чтение

## Файлы в `deploy/`

| Файл | Назначение |
|------|------------|
| `nginx.conf` | Виртуальный хост nginx |
| `monitor-webcrm.service` | systemd unit для uvicorn |
| `.env.production.example` | Шаблон production `.env` |
| `deploy.sh` | Скрипт обновления (git pull → build → restart) |

## Первичная установка

### 1. Пакеты на сервере

```bash
ssh root@77.222.63.161

apt update
apt install -y python3-venv python3-pip nginx git postgresql-client

# Node.js 20 (обязательно для Vite 8)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
node --version   # должно быть v20.x
```

### 2. Копирование кода

**Вариант A — git:**

```bash
mkdir -p /opt/monitor
cd /opt/monitor
git clone git@github.com:mstukalov90-source/Monitor-WebCRM-alpha.git webcrm
```

**Вариант B — rsync с локальной машины:**

```bash
rsync -avz --exclude 'backend/venv' --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' --exclude '.git' --exclude 'tmp' --exclude 'id_rsa' \
  -e "ssh -i <path_to_key>" \
  ./ root@77.222.63.161:/opt/monitor/webcrm/
```

### 3. Backend

```bash
cd /opt/monitor/webcrm/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp ../deploy/.env.production.example .env
chmod 600 .env
```

Заполнить в `.env`:

```bash
# Пароль БД
DB_PASSWORD=<пароль пользователя monitor>

# Случайный ключ сессии (32+ байт в hex)
AUTH_SECRET_KEY=$(openssl rand -hex 32)
```

Полный пример production `.env`:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=monitor
DB_USER=monitor
DB_PASSWORD=<пароль>

LAYERS_CONFIG_PATH=../shared/layers_config.json
CORS_ORIGINS=http://77.222.63.161
GEOJSON_DEFAULT_LIMIT=2000

AUTH_SECRET_KEY=<openssl rand -hex 32>
AUTH_COOKIE_NAME=monitor_session
AUTH_TOKEN_TTL_HOURS=12

PHOTO_STORAGE_DIR=/opt/monitor/downloaded_photo
PHOTO_SFTP_ENABLED=false
PHOTO_LOCAL_CACHE_DIR=./data/photo_cache
```

**Отличия от локальной разработки:**

| Переменная | Dev | Production |
|------------|-----|------------|
| `DB_HOST` | через SSH-туннель `localhost` | `localhost` (БД на сервере) |
| `PHOTO_SFTP_ENABLED` | `true` | `false` |
| `PHOTO_STORAGE_DIR` | не используется | `/opt/monitor/downloaded_photo` |
| `CORS_ORIGINS` | `http://localhost:5173` | `http://77.222.63.161` |

### 4. Миграции CRM

Скрипты идемпотентны (`IF NOT EXISTS`), безопасно запускать повторно:

```bash
cd /opt/monitor/webcrm
export PGPASSWORD=<пароль>
for f in sql/0*.sql; do
  echo "=== $f ==="
  psql -h localhost -U monitor -d monitor -f "$f"
done
```

Проверка:

```bash
psql -h localhost -U monitor -d monitor -c "SELECT PostGIS_Version();"
psql -h localhost -U monitor -d monitor -c "SELECT login, role FROM crm.users LIMIT 5;"
```

### 5. Сборка frontend

```bash
cd /opt/monitor/webcrm/frontend
npm ci
npm run build

mkdir -p /var/www/monitor-webcrm
cp -r dist/* /var/www/monitor-webcrm/
```

### 6. systemd и nginx

```bash
cp /opt/monitor/webcrm/deploy/monitor-webcrm.service /etc/systemd/system/
cp /opt/monitor/webcrm/deploy/nginx.conf /etc/nginx/sites-available/monitor-webcrm
ln -sf /etc/nginx/sites-available/monitor-webcrm /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

chmod +x /opt/monitor/webcrm/deploy/deploy.sh

systemctl daemon-reload
systemctl enable --now monitor-webcrm nginx
```

### 7. Проверка

```bash
# Backend напрямую
curl http://127.0.0.1:8080/health

# Через nginx (важно: server_name = IP, не localhost)
curl http://77.222.63.161/health

# Вход
curl -s -X POST http://77.222.63.161/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"admin","password":"1234"}'
```

В браузере: http://77.222.63.161 → войти как `admin` / `1234` (сменить пароль после первого входа).

## Обновление

На сервере, если код развёрнут через git:

```bash
cd /opt/monitor/webcrm
./deploy/deploy.sh
```

Скрипт выполняет: `git pull` → `pip install` → `npm ci && npm run build` → копирование в `/var/www/monitor-webcrm` → `systemctl restart monitor-webcrm`.

**Обновление через rsync** (без git на сервере):

```bash
# С локальной машины
rsync -avz --exclude 'backend/venv' --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' --exclude '.git' --exclude 'tmp' --exclude 'id_rsa' \
  -e "ssh -i <path_to_key>" \
  ./ root@77.222.63.161:/opt/monitor/webcrm/

# На сервере
ssh root@77.222.63.161 'cd /opt/monitor/webcrm && ./deploy/deploy.sh'
```

При изменении только backend (без frontend):

```bash
cd /opt/monitor/webcrm/backend
source venv/bin/activate && pip install -r requirements.txt
systemctl restart monitor-webcrm
```

## Управление сервисами

```bash
systemctl status monitor-webcrm
systemctl restart monitor-webcrm
journalctl -u monitor-webcrm -f

systemctl status nginx
nginx -t && systemctl reload nginx
```

## Устранение неполадок

### `npm run build` падает с `CustomEvent is not defined`

Установлен Node.js 18. Нужен Node.js 20+:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
```

### `curl http://127.0.0.1/health` → 404, но `http://77.222.63.161/health` работает

В `nginx.conf` указан `server_name 77.222.63.161`. Запросы на `127.0.0.1` не попадают в этот виртуальный хост — это нормально. Проверяйте по IP сервера.

### Фото не отображаются

1. `PHOTO_SFTP_ENABLED=false` в `.env`
2. Файл существует: `ls /opt/monitor/downloaded_photo/<image_name>`
3. Метаданные в БД: `SELECT uuid, image_name FROM genplan.photo_meta WHERE uuid = '...'`
4. Права на чтение каталога для пользователя systemd (`root`)

### Ошибка подключения к БД

PostgreSQL работает в Docker (`monitor-db`). Порт `5432` проброшен на `localhost`:

```bash
docker ps | grep monitor-db
PGPASSWORD=<пароль> psql -h localhost -U monitor -d monitor -c "SELECT 1;"
```

### Сессия не сохраняется

- Frontend и API должны быть на одном origin (`http://77.222.63.161`)
- Cookie `monitor_session`, `SameSite=lax`, без `Secure` (для HTTP по IP)

## Безопасность

- Сменить `AUTH_SECRET_KEY` и пароли тестовых пользователей после установки
- Backend слушает только `127.0.0.1:8080` — снаружи доступен через nginx
- HTTP без шифрования — cookie передаётся открытым текстом; для внутренней сети приемлемо
- При переходе на HTTPS: добавить `secure=True` в cookie ([`backend/app/routes/auth.py`](../backend/app/routes/auth.py)) и обновить `CORS_ORIGINS`

## Совместимость с QGIS

WEBCRM и QGIS-плагин используют одну схему `crm` в БД `monitor`. Задачи, созданные в вебе, видны в QGIS и наоборот.
