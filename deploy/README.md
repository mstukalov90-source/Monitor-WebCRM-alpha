# Деплой MONITOR Web CRM на VPS

Приложение разворачивается на том же сервере, где уже работают PostgreSQL/PostGIS и каталог фотографий. Локальная разработка использует SSH-туннель и SFTP — на VPS эти обходные пути не нужны.

## Продакшен-серверы

Оба сервера работают **независимо** (отдельные `.env`, `AUTH_SECRET_KEY`, сессии):

| Сервер | URL | ОС | nginx config |
|--------|-----|-----|--------------|
| Публичный | http://77.222.63.161 | Ubuntu 24.04 | `/etc/nginx/sites-available/monitor-webcrm` |
| Внутренний | http://172.21.198.219 | RED OS 8 | `/etc/nginx/conf.d/monitor-webcrm.conf` |

## Архитектура (на каждом сервере)

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

| Компонент | Путь / адрес |
|-----------|--------------|
| Код | `/opt/monitor/webcrm/` |
| Backend | `127.0.0.1:8080`, systemd `monitor-webcrm` |
| Frontend | `/var/www/monitor-webcrm/` |
| БД | `localhost:5432`, база `monitor` |
| Фото | `/opt/monitor/downloaded_photo` |

Фронтенд использует относительные URL (`/api/...`). Nginx обязателен.

## Файлы в `deploy/`

| Файл | Назначение |
|------|------------|
| `install.sh` | Первичная установка: `./deploy/install.sh <IP> [DB_PASSWORD]` |
| `deploy.sh` | Обновление: миграции SQL + pip + build + restart |
| `update-both.sh` | rsync + deploy на оба VPS с локальной машины (нужен VPN для 172.21.198.219) |
| `nginx.conf.template` | Шаблон nginx (`__SERVER_IP__`) |
| `.env.production.template` | Шаблон `.env` (`__SERVER_IP__`, `__DB_PASSWORD__`, `__AUTH_SECRET_KEY__`) |
| `monitor-webcrm.service` | systemd unit |
| `nginx.conf` | Пример для 77.222.63.161 (legacy) |

## Первичная установка (рекомендуется)

### 1. Скопировать код на сервер

```bash
# С локальной машины
rsync -avz --exclude 'backend/venv' --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' --exclude '.git' --exclude 'tmp' --exclude 'id_rsa' \
  --exclude '.codegraph' \
  ./ root@<SERVER_IP>:/opt/monitor/webcrm/
```

Или через git:

```bash
mkdir -p /opt/monitor && cd /opt/monitor
git clone git@github.com:mstukalov90-source/Monitor-WebCRM-alpha.git webcrm
```

### 2. Запустить install.sh на сервере

```bash
ssh root@<SERVER_IP>
cd /opt/monitor/webcrm
chmod +x deploy/install.sh deploy/deploy.sh
./deploy/install.sh <SERVER_IP> <DB_PASSWORD>
```

Примеры:

```bash
./deploy/install.sh 77.222.63.161 monitor1
./deploy/install.sh 172.21.198.219 monitor1
```

Скрипт автоматически:
- устанавливает пакеты (`dnf` на RED OS, `apt` + NodeSource на Ubuntu)
- создаёт venv и production `.env` с уникальным `AUTH_SECRET_KEY`
- применяет SQL-миграции `sql/0*.sql`
- собирает frontend и копирует в `/var/www/monitor-webcrm`
- настраивает systemd и nginx

### 3. Проверка

```bash
curl http://<SERVER_IP>/health
curl -s -X POST http://<SERVER_IP>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"admin","password":"1234"}'
```

## Требования к серверу

- Python 3.11+
- **Node.js 20+** (Vite 8; на Ubuntu 24.04 нужен NodeSource, на RED OS 8 — пакет из репозитория)
- nginx, postgresql-client
- PostgreSQL + PostGIS в Docker (`monitor-db`)
- Каталог `/opt/monitor/downloaded_photo`

## Production `.env`

Шаблон: [`.env.production.template`](.env.production.template). Ключевые отличия от dev:

| Переменная | Dev | Production |
|------------|-----|------------|
| `DB_HOST` | SSH-туннель → `localhost` | `localhost` |
| `PHOTO_SFTP_ENABLED` | `true` | `false` |
| `PHOTO_STORAGE_DIR` | — | `/opt/monitor/downloaded_photo` |
| `CORS_ORIGINS` | `http://localhost:5173` | `http://<SERVER_IP>` |

## Обновление

На сервере:

```bash
cd /opt/monitor/webcrm && ./deploy/deploy.sh
```

`deploy.sh` автоматически:
- дописывает в `.env` недостающие ключи (`FIELD_PHOTO_*`)
- применяет **только новые** SQL-миграции из `sql/[0-9]*.sql` (учёт в `webcrm.schema_migrations`)
- на существующем prod при первом deploy после обновления — bootstrap: помечает уже применённые миграции без повторного выполнения
- обновляет Python-зависимости, собирает frontend, перезапускает backend

### SQL-миграции

| Каталог | Назначение |
|---------|------------|
| `sql/[0-9]*.sql` | Идемпотентные миграции схемы — применяются автоматически при deploy |
| `sql/one_time/` | Одноразовые деструктивные скрипты (DELETE `crm.tasks`) — **не** в deploy |

Одноразовые миграции запускаются вручную:

```bash
# Dry-run / малый объём (28_cleanup abort при >100 без флага):
./scripts/run_one_time_migration.sh sql/one_time/28_cleanup_link_orphan_tasks.sql

# Явное подтверждение массового DELETE:
ALLOW_DESTRUCTIVE_MIGRATION=1 ./scripts/run_one_time_migration.sh sql/one_time/28_cleanup_link_orphan_tasks.sql
```

Подробнее: [`sql/one_time/README.md`](../sql/one_time/README.md), [`docs/webcrm_tasks_deletion_investigation.md`](../docs/webcrm_tasks_deletion_investigation.md).

### Smoke-test после deploy

```sql
-- Нет новых удалений задач
SELECT count(*) FROM crm.tasks_deletion_log
WHERE deleted_at > NOW() - INTERVAL '10 minutes';

-- Scoped ETL-задачи MONITOR на месте (сравнить count до/после deploy)
SELECT count(*) FROM crm.tasks
WHERE 'etl' = ANY(user_created)
  AND (earthwork_id ~ '^(point|line|polygon):'
    OR oati_id ~ '^(point|line|polygon):'
    OR localwork_id ~ '^(point|line|polygon):'
    OR avr_mos_id ~ '^(point|line|polygon):');

-- Учёт миграций
SELECT filename FROM webcrm.schema_migrations ORDER BY filename;
```

Повторный `./deploy/deploy.sh` должен выводить `skip ... (already applied)` для всех файлов.

**Оба сервера с локальной машины** (VPN для 172.21.198.219):

```bash
./deploy/update-both.sh
```

Через rsync вручную (без git на сервере):

```bash
rsync -avz ... ./ root@<SERVER_IP>:/opt/monitor/webcrm/
ssh root@<SERVER_IP> 'cd /opt/monitor/webcrm && ./deploy/deploy.sh'
```

## Управление сервисами

```bash
systemctl status monitor-webcrm
systemctl restart monitor-webcrm
journalctl -u monitor-webcrm -f
nginx -t && systemctl reload nginx
```

## Устранение неполадок

### `npm run build` — `CustomEvent is not defined` (Ubuntu)

Node.js 18. Установить Node 20+ через NodeSource (см. `install.sh`).

### `curl http://127.0.0.1/health` → 404

В nginx указан `server_name <SERVER_IP>`. Проверяйте по IP сервера, не по `127.0.0.1`.

### RED OS: nginx config в `conf.d/`

На RED OS нет `sites-available` — `install.sh` пишет в `/etc/nginx/conf.d/monitor-webcrm.conf`.

### Фото не отображаются

1. `PHOTO_SFTP_ENABLED=false`
2. Файл на диске: `ls /opt/monitor/downloaded_photo/<image_name>`
3. Совпадение с БД: `SELECT uuid, image_name FROM genplan.photo_meta WHERE uuid = '...'`

Не все записи в `photo_meta` имеют файл на диске — это нормально для неполного набора фото.

### Ошибка подключения к БД

```bash
docker ps | grep monitor-db
PGPASSWORD=<пароль> psql -h localhost -U monitor -d monitor -c "SELECT 1;"
```

## Безопасность

- Уникальный `AUTH_SECRET_KEY` на каждом сервере
- Backend только на `127.0.0.1:8080`
- HTTP без шифрования — для внутренней сети; при HTTPS обновить cookie и `CORS_ORIGINS`

## Совместимость с QGIS

WEBCRM и QGIS-плагин используют одну схему `crm` в БД `monitor` на каждом сервере независимо.
