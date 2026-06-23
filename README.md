# Monitor Web CRM

Веб-версия CRM для проекта Monitor: карта Leaflet + сбор задач по району + исполнение задач. Совместима с QGIS-плагином [MONITOR_QGIS](../MONITOR_QGIS) и БД [MONITOR](../MONITOR).

## Возможности MVP

- Карта Leaflet с слоями из `shared/layers_config.json`
- Загрузка GeoJSON по видимой области карты (bbox)
- Список районов из `odh_export.hood`
- **Вход** по логину/паролю из `crm.users` (роли `admin`, `field`, `office`, `manager`)
- **Получить задачу** — сбор объектов по району (логика как в QGIS-плагине)
- Запись в `crm.tasks`, скрытие отправленных задач
- **Исполнить задачу** — сопоставление ID, поля станции, отправка в поле / закрытие
- **Персонал** (manager/admin) — районы сотрудников и назначение задач

## Структура

```
MONITOR_WEBCRM/
├── shared/layers_config.json   # конфиг слоёв и CRM
├── sql/01_crm_schema.sql       # схема crm.*
├── sql/05_crm_users.sql        # пользователи crm.users
├── sql/06_task_user_audit.sql  # user_created / user_last_edit
├── sql/07_task_executor.sql    # executor в tasks_field / tasks_area
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
psql -h localhost -U monitor -d monitor -f sql/05_crm_users.sql
psql -h localhost -U monitor -d monitor -f sql/06_task_user_audit.sql
psql -h localhost -U monitor -d monitor -f sql/07_task_executor.sql
```

### 3. Backend

```bash
cd backend
cp .env.example .env
# Укажите DB_PASSWORD и AUTH_SECRET_KEY в .env
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

## Вход и роли

Пароль проверяется в БД (`crm.users`, bcrypt через `pgcrypto`). Сессия — httpOnly cookie.

Тестовые пользователи (после `05_crm_users.sql`), пароль `1234`:

| Логин | Роль | Районы (gid в hood) |
|-------|------|---------------------|
| `admin` | admin | все |
| `vasya` | field | 20, 62 |
| `gena` | office | 20, 62 |
| `lena` | manager | 20, 62 |

| Роль | Задачи | Площадные |
|------|--------|-----------|
| `admin` | все вкладки | все статусы |
| `field` | только «В поле» | только wip |
| `office` | только «Активные» | wip и done |
| `manager` | все вкладки | все статусы |

Роль `field` не выполняет сбор из слоёв — только загрузка снимка «В поле». Роли `manager` и `admin` имеют доступ к странице **Персонал** (управление районами сотрудников и назначение задач).

## Назначение исполнителя (executor)

В таблицах `crm.tasks_field` и `crm.tasks_area` поле `executor` — логин сотрудника (`crm.users.login`, роли `field` / `office`).

- Менеджер/админ назначает задачи на экране «Персонал».
- Сотрудник `field` видит только задачи, где `executor` = его логин **или** `executor IS NULL` (неназначенные).
- Роли `office`, `manager`, `admin` видят все задачи в районе без фильтра по `executor`.

## Аудит задач

В таблицах `crm.tasks`, `tasks_field`, `tasks_done_*`, `tasks_clear`, `tasks_area` поля:

- `user_created` — `TEXT[]` = `[login, ISO-дата UTC]` при создании записи
- `user_last_edit` — `TEXT[]` = `[login, ISO-дата UTC]` при последнем изменении

Заполняются автоматически из сессии пользователя при сборе, PATCH, отправке в поле/закрытии и смене статуса площадного заказа.

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка (без авторизации) |
| POST | `/api/auth/login` | Вход |
| POST | `/api/auth/logout` | Выход |
| GET | `/api/auth/me` | Текущий пользователь |
| GET | `/api/config/layers` | Дерево слоёв |
| GET | `/api/districts` | Список районов (с учётом work_zones) |
| GET | `/api/geojson/{layer_key}?bbox=...` | GeoJSON слоя |
| POST | `/api/tasks/collect` | Сбор и сохранение задач |
| GET | `/api/tasks/active?rayon=...` | Активные задачи района |
| PATCH | `/api/tasks/{key}` | Обновление задачи |
| POST | `/api/tasks/{key}/send-to-field` | Отправить в поле |
| GET | `/api/personnel/users` | Список сотрудников (manager/admin) |
| POST | `/api/personnel/users` | Создать сотрудника (только admin) |
| PATCH | `/api/personnel/users/{uuid}` | Обновить work_zones |
| GET | `/api/personnel/districts` | Районы с gid |
| GET | `/api/personnel/tasks/field` | Задачи tasks_field для назначения |
| GET | `/api/personnel/tasks/active` | Активные задачи для управления (manager/admin) |
| GET | `/api/personnel/tasks/clear` | Задачи «разрывие отсутствует» (manager/admin) |
| GET | `/api/personnel/tasks/area` | Задачи tasks_area для назначения |
| POST | `/api/personnel/tasks/bulk-assign` | Массовое назначение executor |
| POST | `/api/personnel/tasks/bulk-status` | Массовая смена статуса (active/field/clear) |
| POST | `/api/tasks/{key}/return-to-active` | Вернуть задачу из «В поле» в активные |

Все `/api/*` кроме `/api/auth/login` требуют активной сессии.

## Smoke-test

1. Войти как `admin` / `1234`
2. Карта Москвы, слои загружаются при перемещении
3. Выбрать район → «Получить задачу»
4. Клик по строке в таблице → зум на карте
5. «Исполнить задачу» → «На карте» для link-поля → «Отправить в поле»
6. Войти как `vasya` — только 2 района, вкладки «В поле» и «Площадные — на обследовании», без кнопки сбора
7. Войти как `gena` — «Активные» + площадные wip/done
8. Войти как `lena` (manager) → «Персонал» → изменить районы `vasya`, назначить задачу из `tasks_field`
9. Войти как `vasya` — видны только свои и неназначенные задачи в поле
10. Войти как `admin` → «Персонал» → «Добавить сотрудника» → создать пользователя `test_field` (роль field); войти под новым логином
11. Войти как `admin` или `lena` → «Персонал» → вкладка «Активные» → выбрать задачи → «В поле» → на карте задачи появляются во вкладке «В поле»
12. На вкладке «В поле» → выбрать задачи → назначить исполнителя из списка → «В активные» или «Разрывие отсутствует»

```sql
SELECT * FROM crm.tasks_field ORDER BY sent_at DESC LIMIT 5;
```

## Совместимость

WEBCRM и QGIS-плагин используют одну схему `crm` в БД `monitor`. Задачи, созданные в вебе, видны в QGIS и наоборот. Правила ролей совпадают с QGIS-плагином.
