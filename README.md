# Monitor Web CRM

Веб-версия CRM для проекта Monitor: карта Leaflet + сбор задач по району + исполнение задач. Совместима с QGIS-плагином [MONITOR_QGIS](../MONITOR_QGIS) и БД [MONITOR](../MONITOR).

## Возможности MVP

- Карта Leaflet с слоями из `shared/layers_config.json`
- Загрузка GeoJSON по видимой области карты (bbox)
- Список районов из `odh_export.hood`
- **Получить задачу** — сбор объектов по району (логика как в QGIS-плагине)
- Запись в `crm.tasks`, скрытие отправленных задач
- **Исполнить задачу** — сопоставление ID, поля станции, отправка в поле / закрытие

## Структура

```
MONITOR_WEBCRM/
├── shared/layers_config.json   # конфиг слоёв и CRM
├── sql/01_crm_schema.sql       # схема crm.*
├── backend/                    # FastAPI :8080
└── frontend/                   # Vite + React :5173
```

## Локальный запуск

### 1. SSH-туннель к БД

```bash
ssh -i <path_to_key> -L 5432:127.0.0.1:5432 root@77.222.63.161
```

### 2. Миграция CRM (если схема ещё не создана)

```bash
psql -h localhost -U monitor -d monitor -f sql/01_crm_schema.sql
```

### 3. Backend

```bash
cd backend
cp .env.example .env
# Укажите DB_PASSWORD в .env
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Откройте http://localhost:5173

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка |
| GET | `/api/config/layers` | Дерево слоёв |
| GET | `/api/districts` | Список районов |
| GET | `/api/geojson/{layer_key}?bbox=...` | GeoJSON слоя |
| POST | `/api/tasks/collect` | Сбор и сохранение задач |
| GET | `/api/tasks/active?rayon=...` | Активные задачи района |
| PATCH | `/api/tasks/{key}` | Обновление задачи |
| POST | `/api/tasks/{key}/send-to-field` | Отправить в поле |

## Smoke-test

1. Карта Москвы, слои загружаются при перемещении
2. Выбрать район → «Получить задачу»
3. Клик по строке в таблице → зум на карте
4. «Исполнить задачу» → «На карте» для link-поля → «Отправить в поле»
5. Повторный сбор — задача скрыта из списка

```sql
SELECT * FROM crm.tasks_field ORDER BY sent_at DESC LIMIT 5;
```

## Совместимость

WEBCRM и QGIS-плагин используют одну схему `crm` в БД `monitor`. Задачи, созданные в вебе, видны в QGIS и наоборот.
