# Движок маршрутов обследования (OSRM) — контракт для Android

**Аудитория:** команда Android (полевое приложение)  
**Версия:** 2026-09-07  
**Прод:** `http://172.21.198.219` (LAN). Внешний API `monitor-crm.mggt.ru` этот функционал не отдаёт.  
**Код:** [`backend/app/crm/order_route.py`](../backend/app/crm/order_route.py), HTTP [`backend/app/routes/order_routes.py`](../backend/app/routes/order_routes.py)

На устройстве **не нужно** поднимать OSRM и PostGIS. Маршрут строит WebCRM; приложение запрашивает готовый трек (JSON / GPX) и ведёт по нему полевика.

---

## 1. Задача обследования

Площадной заказ — полигон `crm.tasks_area.geom` (EPSG:4326). Плановый маршрут должен:

1. Пройти так, чтобы **каждая задача внутри полигона** оказалась в буфере **100 м** от линии маршрута.
2. С буфером **100 м** вокруг линии **покрыть полигон заказа** (цель — 100%; на графе дорог OSRM это не всегда достижимо).

Метрика площади — CRS **EPSG:32637** (как в `crm_tasks.metric_crs`). Буфер и покрытие считаются в метрах на этой проекции, геометрия клиенту отдаётся в **WGS84, GeoJSON `[longitude, latitude]`**.

Покрытие **&lt; 95%** — штатная ситуация (дворы вне графа, разрывы сети), не ошибка API. Непокрытые куски приходят в `uncovered_geometry` (рисовать красным).

---

## 2. Как устроен движок (сервер)

```
Заказ (полигон) + задачи внутри
        │
        ▼
Точки задач (ST_PointOnSurface) + сетка покрытия (ST_GeneratePoints, шаг ~180 м)
        │
        ▼
Дедуп (~30 м) → truncate ≤ 300 точек
        │
        ▼
Snap к графу OSRM foot (nearest, отброс если > 500 м от сети)
        │
        ▼
OSRM Trip (foot, roundtrip=false, source=first), чанки по 90 точек
        │
        ▼
Проверка PostGIS: % полигона в буфере 100 м, % задач в буфере
        │
        ├── ≥ 95% покрытия полигона → сохранить
        └── иначе до 3 итераций: центроиды «дыр» → snap (foot, иначе bike) → снова Trip
```

**Профили OSRM на прод .219** (только localhost сервера):

| Контейнер | Порт | Профиль в URL |
|-----------|------|----------------|
| `monitor-osrm-car` | `127.0.0.1:5000` | `driving` |
| `monitor-osrm-bicycle` | `127.0.0.1:5001` | `bicycle` / `bike` |
| `monitor-osrm-foot` | `127.0.0.1:5002` | `foot` |

Текущая реализация **ведёт обход пешком (`foot`)**. Профиль `bike` используется только как fallback snap для точек в «дырах» покрытия. `driving` в сборке маршрута **не вызывается** (зарезервирован в конфиге).

Константы движка:

| Имя | Значение | Смысл |
|-----|----------|--------|
| `ORDER_ROUTE_BUFFER_M` | 100 | Радиус покрытия линии |
| `ORDER_ROUTE_GRID_M` | 180 | Плотность случайной сетки внутри полигона |
| `MAX_WAYPOINTS` | 300 | Потолок точек после дедупа |
| `OSRM_TRIP_CHUNK` | 90 | Размер чанка `/trip` |
| `MAX_REFINE_ITERATIONS` | 3 | Дожим непокрытых зон |
| Snap max | 500 м | Дальше точка отбрасывается |
| Refine stop | ≥ 95% `polygon_coverage_pct` | Дальше не крутим |

Источники геометрии задач (не колонка `tasks_field.geom`): union `crm.office_task_points`, полевые отчёты, `items_*` по `task_key`. Точка для маршрута — `ST_PointOnSurface` (корректно для Point / MultiPoint / линия / полигон).

Результат **upsert** в `crm.order_routes` по `order_key` (один сохранённый маршрут на заказ). Повторный POST перезаписывает.

---

## 3. Аутентификация (как у QGIS)

См. также [qgis_letters_api.md](qgis_letters_api.md) §3.

`POST {base}/api/auth/login`  
`Content-Type: application/json`

```json
{ "login": "field_user", "password": "..." }
```

В ответе 200 поле **`token`**. Дальше:

```
Authorization: Bearer <token>
```

Cookie можно игнорировать.

**Текущие права API маршрутов:** роли **`field`**, **`manager`**, **`admin`**. Роль **`office` — 403**. У `field` дополнительно проверяется район заказа (`work_zones` / `check_rayon`): чужой район → 403.

Перед показом UI маршрутов в Android проверьте `role === "field"` (или manager/admin). Cookie в ответе login можно игнорировать.

TTL токена: `AUTH_TOKEN_TTL_HOURS` (прод: 12 ч). При 401 — повторный login.

---

## 4. HTTP API

Base: `http://172.21.198.219` (без завершающего `/`).  
`{key}` — UUID `crm.tasks_area.key`.

Таймаут клиента на **POST build-route: 120 с** (на больших полигонах много вызовов OSRM nearest). GET — обычные 15–30 с.

### 4.1. Построить и сохранить

`POST /api/crm/tasks-area/{key}/build-route`

Тело (все поля опциональны):

```json
{
  "start_lng": 37.6173,
  "start_lat": 55.7558
}
```

Если старт не передан, обход начинается с точек задач/сетки (порядок Trip OSRM, `source=first` — первая точка списка после дедупа).

**Успех 200** — объект маршрута (схема ниже).  
**404** — нет заказа или нет `geom`.  
**400** — мало точек (≥2 после snap), сеть OSRM не приняла точки, Trip пустой.  
**403** — роль не `field`/`manager`/`admin`, либо район заказа вне `work_zones` полевика.  
**500** — сбой PostGIS/OSRM; `detail` — текст ошибки.

### 4.2. Последний сохранённый маршрут

`GET /api/crm/tasks-area/{key}/route`

**404** — `Маршрут ещё не построен` (ещё не было успешного POST).

### 4.3. GPX для навигации

`GET /api/crm/tasks-area/{key}/route.gpx`  
`Accept` не обязателен.  
`Content-Type: application/gpx+xml`  
`Content-Disposition: attachment; filename="route_<8 символов uuid>.gpx"`

GPX 1.1, один `<trk>` / `<trkseg>`, точки `lat`/`lon` (не lng-lat JSON). Подходит для импорта в OSMAnd / органического трека на карте.

### 4.4. GeoJSON-пакет слоёв

`GET /api/crm/tasks-area/{key}/route.geojson`

`FeatureCollection`, свойство `properties.layer`:

| `layer` | Геометрия | Назначение в UI |
|---------|-----------|-----------------|
| `route` | LineString / MultiLineString | Линия маршрута |
| `buffer` | MultiPolygon | Буфер 100 м |
| `order_polygon` | Polygon / MultiPolygon | Контур заказа |
| `uncovered` | Polygon / Geometry | Дыры покрытия (может отсутствовать / быть пустым) |

---

## 5. JSON маршрута (`OrderRouteContext`)

Координаты везде **GeoJSON: `[lng, lat]`**. На Android для `LatLng` менять местами.

```json
{
  "order_key": "2179241b-0bef-429d-8a9b-b5f79c90b0e8",
  "order": {
    "task_number": "М/ВАО-26-3/Измайлово-7",
    "rayon": "Измайлово",
    "geometry": { "type": "Polygon", "coordinates": [ [ [37.77, 55.79], "..." ] ] }
  },
  "route_geometry": {
    "type": "LineString",
    "coordinates": [ [37.7701, 55.7912], [37.7704, 55.7915] ]
  },
  "buffer_geometry": { "type": "MultiPolygon", "coordinates": [] },
  "uncovered_geometry": null,
  "segments": [
    {
      "profile": "foot",
      "chunk_index": 0,
      "distance_m": 1495.4,
      "duration_s": 1076.4,
      "waypoint_count": 12
    }
  ],
  "task_coverage_pct": 100.0,
  "polygon_coverage_pct": 98.24,
  "tasks_total": 2,
  "tasks_covered": 2,
  "buffer_m": 100,
  "total_distance_m": 1495.4,
  "total_duration_s": 1076.4,
  "built_by": "admin",
  "built_at": "2026-09-04T05:26:00+00:00"
}
```

| Поле | Смысл для Android |
|------|-------------------|
| `route_geometry` | Основной трек. После GET сохранённого маршрута тип может быть `MultiLineString` (как в БД). |
| `buffer_m` | Не хардкодить 100 — брать из ответа. |
| `polygon_coverage_pct` | Показать оператору; предупреждение если &lt; 95. |
| `task_coverage_pct` / `tasks_total` | Сколько задач «закрыто» буфером. |
| `total_duration_s` | Оценка **пешком** по графу OSRM, не GPS. |
| `tasks_covered` | После GET сохранённого маршрута может быть `null` (в таблице не хранится отдельно). |
| `uncovered_geometry` | Опционально; `ST_Difference`, может быть GeometryCollection. |

Идемпотентность: повторный build для того же `order_key` затирает предыдущий трек.

---

## 6. Список заказов для выбора

Маршрут привязан к **площадному заказу**, не к точечной `crm.tasks`.

`GET /api/tasks/area?rayon={название района}`  
(нужна сессия той же учётки; район — как в `hood`).

В `groups[].subgroups[].features[]`:

- `task_key` или `attributes.key` — UUID для `{key}` в URL маршрута;
- `geometry` — полигон заказа;
- `attributes.task_number`, `attributes.status`, `attributes.rayon`.

WebCRM UI: экран «Маршруты обследования» (кнопка на стартовой странице района).

---

## 7. Рекомендуемый поток Android

1. Login → сохранить JWT.  
2. Выбор района (как в существующем полевом клиенте).  
3. Список заказов `GET /api/tasks/area`.  
4. `GET .../route` — если 200, показать трек без пересчёта; если 404 — кнопка «Построить».  
5. `POST .../build-route` (опционально GPS как `start_lat`/`start_lng`). Индикатор 1–2 минуты.  
6. Навигация: либо полилиния из `route_geometry`, либо скачать GPX (`GET .../route.gpx`) и открыть во внешнем навигаторе.  
7. Опционально слой `buffer_geometry` / `uncovered_geometry` для контроля покрытия.  
8. Не слать build на каждый запуск экрана — только по действию пользователя или если GET 404.

**Координаты старта:** `start_lng` / `start_lat` в теле POST — долгота, широта (не наоборот).

---

## 8. Ограничения (важно для мобильного клиента)

1. **Права.** API: `field`, `manager`, `admin`. Полевик видит только заказы своих районов (`check_rayon`). `office` — 403.  
2. **Нет стриминга.** Один синхронный POST до конца расчёта.  
3. **Нет версий маршрута.** Один ряд на заказ.  
4. **Граф ≠ дворы.** 100% покрытия полигона не обещаем.  
5. **OSRM недоступен с телефона.** Порты 5000–5002 слушают `127.0.0.1` на .219. Клиент ходит только в WebCRM `:80` → uvicorn.  
6. **nginx timeout.** Если POST с LAN рвётся ~60 с, повторить или увеличить timeout прокси; WebCRM frontend ставит 120 с на свой `fetch`.  
7. **Большие полигоны.** Сетка режется до 300 точек — покрытие может быть грубее.

---

## 8.1. Что не копировать в Android

Не повторять: `ST_GeneratePoints`, snap nearest, Trip, буфер покрытия. Это серверный пайплайн. На устройстве — отрисовка, следование линии, запись фактического GPS-трека (фактические треки живут в `mggt_field.tracks`, это **другой** контур, оценка качества в WebCRM).

---

## 9. Примеры curl

```bash
BASE=http://172.21.198.219
KEY=2179241b-0bef-429d-8a9b-b5f79c90b0e8

TOKEN=$(curl -sS -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"login":"admin","password":"..."}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# список заказов района
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/tasks/area?rayon=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("Измайлово"))')"

# построить (до 120 с)
curl -sS -m 120 -X POST "$BASE/api/crm/tasks-area/$KEY/build-route" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"start_lng":37.77,"start_lat":55.79}'

curl -sS -H "Authorization: Bearer $TOKEN" \
  -o route.gpx "$BASE/api/crm/tasks-area/$KEY/route.gpx"
```

---

## 10. Файлы в репозитории

| Файл | Роль |
|------|------|
| `backend/app/crm/order_route.py` | Алгоритм, PostGIS, upsert |
| `backend/app/routing/osrm_client.py` | `nearest` / `route` / `trip` |
| `backend/app/routing/gpx_export.py` | GPX 1.1 из GeoJSON |
| `backend/app/routes/order_routes.py` | HTTP |
| `sql/43_order_routes.sql` | Таблица `crm.order_routes` |
| `frontend/src/components/OrderRoutesScreen.tsx` | Эталон UI (список → карта → GPX) |

Конфиг сервера: `OSRM_FOOT_URL`, `OSRM_BIKE_URL`, `OSRM_DRIVING_URL`, `OSRM_TIMEOUT_SECONDS`, `ORDER_ROUTE_BUFFER_M`, `ORDER_ROUTE_GRID_M` в `backend/.env`.
