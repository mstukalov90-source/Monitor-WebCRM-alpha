# Деплой MONITOR Web CRM на VPS

Приложение разворачивается на том же сервере, где уже работают PostgreSQL/PostGIS, MONITOR API и каталог фотографий. Локальная разработка использует SSH-туннель и SFTP — на VPS эти обходные пути не нужны.

## Адреса и роли

Серверы работают **независимо** (отдельные `.env`, `AUTH_SECRET_KEY`, сессии):

| Адрес | Роль | ОС | nginx |
|-------|------|-----|-------|
| **http://172.21.198.219** | **Прод WebCRM** (веб-приложение, внутренняя сеть) | RED OS 8 | `/etc/nginx/conf.d/monitor-webcrm.conf` |
| **http://monitor-crm.mggt.ru** | **API из интернета** (тот же хост; наружу открыт только API) | — | тот же conf, **не менять** из WebCRM-деплоя |
| **http://77.222.63.161** | **Только тестирование** WebCRM | Ubuntu 24.04 | `/etc/nginx/sites-available/monitor-webcrm` |

Hostname прода: `LEN-MOSTRRAB-DCR-01P`.

## Архитектура прода (172.21.198.219)

Один хост: WebCRM + MONITOR API (`monitor-api`) + PostgreSQL + фото.

```
Браузер (LAN)                    Интернет
   │                                  │
   ▼                                  ▼
http://172.21.198.219          http://monitor-crm.mggt.ru
   │                                  │
   └──────────── nginx :80 ───────────┘
         │                      │
         │ geo: только LAN      │ без geo (внешний API)
         ▼                      ▼
   SPA + /api/* ──► uvicorn    /health, /api/photos|uuids|mggtfield
                   :8080       ──► monitor-api :8000
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  PostgreSQL   downloaded_photo  layers_config.json
  :5432        mggtfield_photo
```

| Компонент | Путь / адрес |
|-----------|--------------|
| Код | `/opt/monitor/webcrm/` |
| Backend WebCRM | `127.0.0.1:8080`, systemd `monitor-webcrm` |
| Frontend | `/var/www/monitor-webcrm/` |
| MONITOR API | `127.0.0.1:8000` (Docker `monitor-api`) |
| БД | `localhost:5432`, база `monitor` (Docker `monitor-db`) |
| Фото | `/opt/monitor/downloaded_photo`, `/opt/monitor/mggtfield_photo` |

Фронтенд использует относительные URL (`/api/...`). Nginx обязателен.

**Не перезаписывать** nginx на проде шаблоном `nginx.conf.template` или шагом nginx из `install.sh` — сломается раздача внешнего API.

### Проверка здоровья

| URL | Что отвечает |
|-----|--------------|
| `http://172.21.198.219/health` или `http://monitor-crm.mggt.ru/health` | MONITOR API (`:8000`), **не** WebCRM |
| `curl http://127.0.0.1:8080/health` **на сервере** | WebCRM |

## Файлы в `deploy/`

| Файл | Назначение |
|------|------------|
| `install.sh` | Первичная установка: `./deploy/install.sh <IP> [DB_PASSWORD]` (для **тест**-стенда; на прод 219 — с осторожностью, без nginx-шага) |
| `deploy.sh` | Обновление: миграции SQL + pip + build + restart |
| `update-both.sh` | rsync + deploy на прод и тест (VPN для 172.21.198.219) |
| `nginx.conf.template` | Шаблон nginx для **простого** стенда (`__SERVER_IP__`) — не для прода 219 |
| `.env.production.template` | Шаблон `.env` (`__SERVER_IP__`, `__DB_PASSWORD__`, `__AUTH_SECRET_KEY__`) |
| `monitor-webcrm.service` | systemd unit |
| `nginx.conf` | Пример для 77.222.63.161 (тест) |

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
# Тест-стенд
./deploy/install.sh 77.222.63.161 monitor1

# Прод: только если поднимаете с нуля; nginx conf на 219 уже кастомный — не перезаписывать
./deploy/install.sh 172.21.198.219 monitor1
```

Скрипт автоматически:
- устанавливает пакеты (`dnf` на RED OS, `apt` + NodeSource на Ubuntu)
- создаёт venv и production `.env` с уникальным `AUTH_SECRET_KEY`
- применяет SQL-миграции `sql/0*.sql`
- собирает frontend и копирует в `/var/www/monitor-webcrm`
- настраивает systemd и nginx (на проде 219 nginx уже настроен вручную)

### 3. Проверка

```bash
# WebCRM (на сервере)
curl http://127.0.0.1:8080/health

# Логин WebCRM с машины в LAN (прод) или с тест-стенда
curl -s -X POST http://172.21.198.219/api/auth/login \
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
| `DB_HOST` | SSH-туннель → `localhost` | `localhost` / `127.0.0.1` |
| `PHOTO_SFTP_ENABLED` | `true` | `false` |
| `PHOTO_STORAGE_DIR` | — | `/opt/monitor/downloaded_photo` |
| `CORS_ORIGINS` | `http://localhost:5173` | `http://<SERVER_IP>` |
| `AUTH_SECRET_KEY` | любой | **обязателен**, уникальный на каждом сервере |

Без `AUTH_SECRET_KEY` backend подставляет небезопасный дефолт из кода — на проде недопустимо. `deploy.sh` допишет ключ, если его нет.

## Обновление

На сервере:

```bash
cd /opt/monitor/webcrm && ./deploy/deploy.sh
```

`deploy.sh` автоматически:
- дописывает в `.env` недостающие ключи (`FIELD_PHOTO_*`, `PHOTO_STORAGE_DIR`, OSM/geocode, `AUTH_*` при отсутствии)
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

### Чеклист после переноса / обновления прода (219)

1. `systemctl is-active monitor-webcrm nginx` → `active`
2. `curl http://127.0.0.1:8080/health` → `{"status":"ok"}`
3. В `.env` есть `AUTH_SECRET_KEY`, `PHOTO_STORAGE_DIR`, `PHOTO_SFTP_ENABLED=false`, `EXCEL_UPLOAD_DIR=/opt/monitor/excel_inbox`
4. Миграции: `SELECT filename FROM webcrm.schema_migrations ORDER BY filename;`
5. Фото: каталоги `/opt/monitor/downloaded_photo` и `/opt/monitor/mggtfield_photo`
6. Excel для второго приложения: каталог `/opt/monitor/excel_inbox`, страница `http://172.21.198.219/upload`
7. SPA открывается с LAN: `http://172.21.198.219/`
8. Nginx conf для внешнего API **не** менялся

**Прод + тест с локальной машины** (VPN для 172.21.198.219):

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

В nginx указан `server_name`. На проде проверяйте `http://172.21.198.219/...` или `http://127.0.0.1:8080/health` для WebCRM.

### `/health` на :80 — это не WebCRM

На проде `location = /health` проксируется в `monitor-api:8000`. Для WebCRM используйте `127.0.0.1:8080/health`.

### RED OS: nginx config в `conf.d/`

На RED OS нет `sites-available` — conf лежит в `/etc/nginx/conf.d/monitor-webcrm.conf`. На проде он общий с внешним API — не затирать шаблоном из `deploy/`.

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

- Уникальный `AUTH_SECRET_KEY` на каждом сервере (**обязателен**; без него — небезопасный дефолт)
- Backend WebCRM только на `127.0.0.1:8080`
- Внешний API (`monitor-crm.mggt.ru`) и его nginx locations **не менять** из этого репозитория
- WebCRM SPA/`/api/` на проде ограничены внутренней сетью (`geo $is_internal`)
- HTTP без шифрования — для внутренней сети; при HTTPS обновить cookie и `CORS_ORIGINS`

## Совместимость с QGIS

WEBCRM и QGIS-плагин используют одну схему `crm` в БД `monitor` на каждом сервере независимо.
