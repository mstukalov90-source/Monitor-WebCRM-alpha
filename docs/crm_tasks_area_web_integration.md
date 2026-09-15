# `crm.tasks_area` — контракт для веб-интерфейса

Нумерация участков и загрузка полигонов **не являются HTTP API MONITOR**. Это функции PostgreSQL. WebCRM должен ходить в ту же БД `monitor` (схема `crm`) и **не генерировать `task_number` на клиенте**.

Источник правды: `sql/23_crm_tasks_area_quarterly_numbering.sql`.

## Что встраивать

| Задача UI | Что вызывать | Кто владелец значения |
|-----------|--------------|------------------------|
| Создать участок (полигон) | `INSERT INTO crm.tasks_area` | UI задаёт geom + rayon/okrug/okrug_shor |
| Статус новой записи | колонка `status` | UI: `'free'`, если пользователь не задал |
| Номер задания | `CALL crm.refresh_tasks_area_quarterly()` | **только БД** |
| Показать участок | `SELECT` по `key` | `task_number`, `area`, `status` |

Не копируйте алгоритм нумерации в JS/Python UI. Любая ручная сборка строки `М/ЮВАО-26-3/Кузьминки-1` даст дубли.

## Таблица `crm.tasks_area`

PK: `key UUID`. Геометрия: `geom geometry(Geometry, 4326)`.

Колонки, которые UI должен знать:

| Колонка | Тип | Кто пишет | Примечание |
|---------|-----|-----------|------------|
| `key` | UUID | UI или `gen_random_uuid()` | стабильный id в URL |
| `fid`, `gid` | bigint | опционально | из GPKG; дубли `gid` допустимы |
| `rayon`, `okrug`, `okrug_shor` | text | UI, через нормализацию | обязательны для номера |
| `geom` | 4326 | UI | не пустая, лучше `ST_MakeValid` |
| `area` | float | **процедура** | кв. м (`ST_Area(geom::geography)`), не доверять файлу |
| `status` | text | UI | `'free'` / `'wip'` / `'in_pause'` / `'done'` и т.д. |
| `task_number` | text | **процедура** | уникален при `NOT NULL` |
| `loaded_at` | timestamptz | DEFAULT `now()` | |
| `analise` | bool | UI / workflow | DEFAULT `false` |

На проде есть уникальный индекс:

```sql
CREATE UNIQUE INDEX uq_crm_tasks_area_task_number
    ON crm.tasks_area (task_number)
    WHERE task_number IS NOT NULL;
```

Прямой `UPDATE task_number = '…'` без двухфазного NULL упрётся в этот индекс.

## Нормализация имён

Перед INSERT/UPDATE атрибутов:

```sql
crm.normalize_attr_text(rayon)       -- CR/LF → пробел, схлопывание пробелов, ' - ' → '-'
crm.normalize_task_label(rayon)      -- то же + пробелы/дефисы → '_', без краевых '_'
```

Примеры:

| Вход | `normalize_attr_text` | `normalize_task_label` (в номере) |
|------|------------------------|-----------------------------------|
| `Кузьминки` | `Кузьминки` | `Кузьминки` |
| `Филёвский парк` | `Филёвский парк` | `Филёвский_парк` |
| `Юго-Восточный\r\n` | `Юго-Восточный` | `Юго_Восточный` |

В INSERT всегда:

```sql
crm.normalize_attr_text(:rayon),
crm.normalize_attr_text(:okrug),
crm.normalize_attr_text(:okrug_shor)
```

Иначе «Кузьминки» и «Кузьминки » дадут **две** серии номеров.

## Формат `task_number`

```
М/{okrug_label}-{YY}-{Q}/{rayon_label}-{N}
```

Пример: `М/ЮВАО-26-3/Кузьминки-1`

- `YY`, `Q` — **дата запуска процедуры** в `Europe/Moscow`, не дата полигона.
- `okrug_label` / `rayon_label` — `normalize_task_label`.
- `N` — единый счётчик на пару `(okrug_label, rayon_label)` **для всех статусов** (`free`, `wip`, `done`, …).
- Порядок `N`: с севера на юг (`ST_Y(ST_Centroid(geom)) DESC`, затем `key`).

Атрибуты округа/района:

1. Если центроид участка лежит в полигоне `odh_export.hood` и пересечение ≥ 99.9% площади участка — берутся `hood.okrug_shor` / `hood.rayon`.
2. Иначе — колонки самой `tasks_area`.

Поэтому UI может сохранить `rayon=Ростокино`, а номер получит `Останкинский`, если hood так матчится. Это штатно.

Строка без номера: нет `okrug_shor`/`okrug` **и** нет `rayon` после нормализации (процедура пишет WARNING с `key`).

## Рекомендуемый поток UI: создать участок

Одна транзакция. Не коммить INSERT без `refresh`, если UI сразу показывает номер.

```sql
BEGIN;

INSERT INTO crm.tasks_area (
    key, fid, gid, rayon, okrug, okrug_shor, geom, status
) VALUES (
    gen_random_uuid(),
    :fid,
    :gid,
    crm.normalize_attr_text(:rayon),
    crm.normalize_attr_text(:okrug),
    crm.normalize_attr_text(:okrug_shor),
    ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(:geom, 4326)), 3)),
    COALESCE(NULLIF(btrim(:status), ''), 'free')
)
RETURNING key;

-- если CRS источника — МСК-77 (SRID 980077), geom так:
-- ST_Transform(ST_SetSRID(:geom_msk, 980077), 4326)

UPDATE crm.tasks_area SET status = 'free' WHERE status IS NULL;

CALL crm.refresh_tasks_area_quarterly();

COMMIT;

SELECT key, status, task_number, area, rayon, okrug_shor
FROM crm.tasks_area
WHERE key = :new_key;
```

Если файл уже EPSG:4326 — **не** ставить SRID 980077.

Фильтр битой геометрии: `geom IS NOT NULL AND NOT ST_IsEmpty(geom)`.

## Побочные эффекты `refresh` (важно для UI)

`CALL crm.refresh_tasks_area_quarterly()`:

1. Пересчитывает **все** строки с геометрией, не только новую.
2. Обнуляет `task_number`, затем пишет новые значения (из-за unique index).
3. Перезаписывает `area`.
4. Меняет `YY-Q` у **всей** таблицы, если календарный квартал сменился.

Для кнопки «загрузить GPKG» это нормально (так делаются офлайн-загрузки).  
Для кнопки «сохранить один полигон» в середине квартала номера соседей обычно те же (тот же порядок N). На границе квартала (1 янв / 1 апр / 1 июл / 1 окт) **все** номера сменят `YY-Q`.

Автозапуск: pg_cron `0 0 1 1,4,7,10 *` (`sql/24_crm_tasks_area_pg_cron.sql`). UI не должен дублировать cron своим таймером, достаточно вызова после записи геометрии.

Долгий запрос: spatial join на всю таблицу. Для формы сохранения ставьте `statement_timeout` не меньше десятков секунд (на ~700 полигонах процедура укладывается в несколько секунд).

## Что UI **не** должен делать

- Не присваивать `task_number` вручную и не инкрементировать `MAX(N)+1` в приложении.
- Не нумеровать отдельно `free` и `wip` — так как раз появлялись дубли `…-1`.
- Не делать upsert по `gid` (это не уникальный ключ).
- Не копировать `area` из GPKG, если в файле одно число на несколько разных полигонов.

## Проверки после сохранения

```sql
-- дубли номеров (должно быть 0)
SELECT task_number, COUNT(*)
FROM crm.tasks_area
WHERE task_number IS NOT NULL
GROUP BY 1
HAVING COUNT(*) > 1;

-- новые без номера
SELECT key, rayon, okrug_shor
FROM crm.tasks_area
WHERE geom IS NOT NULL
  AND (task_number IS NULL OR btrim(task_number) = '');
```

HTTP-ошибка unique_violation (`23505` на `uq_crm_tasks_area_task_number`) = в UI пытались записать номер мимо процедуры или параллельно два refresh без блокировки. Вызывать процедуру **сериально** (advisory lock):

```sql
SELECT pg_advisory_xact_lock(hashtext('crm.refresh_tasks_area_quarterly'));
CALL crm.refresh_tasks_area_quarterly();
```

## Связь с карточками `crm.tasks`

После появления/изменения полигонов участков можно перепривязать задачи:

```sql
CALL crm.refresh_task_area_keys();  -- sql/39_crm_tasks_area_key.sql
```

Пишет `crm.tasks.area_key UUID[]` (пересечение геометрии задачи с участком). Это отдельный шаг, не часть нумерации.

## Черновик HTTP для WebCRM (ещё нет в MONITOR)

Имеет смысл один endpoint, который делает INSERT + lock + CALL + SELECT.

`POST /api/crm/tasks-area`

Тело:

```json
{
  "gid": 98,
  "rayon": "Кузьминки",
  "okrug": "Юго-Восточный административный округ",
  "okrug_shor": "ЮВАО",
  "status": "free",
  "geom": { "type": "MultiPolygon", "coordinates": [ "…" ] }
}
```

Ответ 201:

```json
{
  "key": "2b1f33bc-7a7d-40c4-95f8-7a10d456d02b",
  "status": "free",
  "task_number": "М/ЮВАО-26-3/Кузьминки-1",
  "area": 1150665.8,
  "rayon": "Кузьминки",
  "okrug_shor": "ЮВАО"
}
```

`geom`: GeoJSON EPSG:4326. Поле `task_number` в запросе игнорировать.

Массовая загрузка файла: тот же пайплайн пачкой INSERT, один `CALL` в конце, не refresh на каждую строку.

## Код на стороне БД

- Таблица: `sql/18_crm_tasks_area.sql`
- Флаг analise: `sql/22_crm_tasks_area_analise.sql`
- Нормализация + процедура: `sql/23_crm_tasks_area_quarterly_numbering.sql`
- Квартальный cron: `sql/24_crm_tasks_area_pg_cron.sql`
- Разовое разведение старых дублей: `sql/27_crm_tasks_area_fix_dup_task_numbers.sql`
- `area_key` у `crm.tasks`: `sql/39_crm_tasks_area_key.sql`
