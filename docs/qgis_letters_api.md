# Интеграция QGIS-модуля с API писем ОАТИ (MONITOR WebCRM)

**Аудитория:** разработчик QGIS-плагина  
**Версия:** 2026-08-10  
**Назначение:** вызвать WebCRM по HTTP для формирования DOCX-письма ОАТИ (геокод, шаблон, ситуационный план, вложения фото). Остальной CRM — по-прежнему прямой доступ к БД `monitor` (см. [qgis_module_data_contract.md](qgis_module_data_contract.md)).

---

## 1. Границы ответственности


| Что делает плагин | Как |
| ----------------- | --- |
| Задачи, статусы, районы, персонал | SQL / PostGIS к БД `monitor` |
| Письма ОАТИ (DOCX) | **HTTP API WebCRM** (этот документ) |


Повторять генерацию письма в QGIS (шаблон Word, тайлы карты, SFTP-фото) **не нужно** — сервер WebCRM уже умеет это.

---

## 2. Предусловия

1. **Base URL** инстанса WebCRM (без завершающего `/`), например `http://172.21.198.219` или тестовый хост.
2. Учётная запись из `crm.users` с ролью **`office`**, **`manager`** или **`admin`**. У field `can_generate_letters = false` → API ответит **403**.
3. У задачи есть полевой отчёт:
   - `task_key` = `crm.tasks.key` (UUID);
   - `report_id` = `mggt_field.reports.id`, где `tasks_key = task_key`.
4. У отчёта есть геометрия (иначе draft/generate вернут 400).

Пример выбора отчётов из БД (в плагине):

```sql
SELECT id, created_at, comm_type
FROM mggt_field.reports
WHERE tasks_key = :task_key::uuid
ORDER BY created_at DESC NULLS LAST, id DESC;
```

---

## 3. Аутентификация

WebCRM для браузера кладёт JWT в httpOnly-cookie. Для QGIS используйте **Bearer**.

### 3.1. Вход

`POST {base}/api/auth/login`  
`Content-Type: application/json`

**Тело:**

```json
{ "login": "gena", "password": "..." }
```

**Успех 200** — поля пользователя + **`token`** (JWT):

```json
{
  "login": "gena",
  "role": "office",
  "work_zones": [12, 34],
  "allowed_task_sources": ["active", "field", "delay", "done_legal", "done_illegal", "clear", "area"],
  "default_task_source": "active",
  "can_collect": true,
  "can_manage_personnel": false,
  "can_generate_letters": true,
  "can_manage_field_task_status": true,
  "can_postpone_tasks": true,
  "can_create_users": false,
  "token": "<jwt>"
}
```

Перед показом UI писем проверьте `can_generate_letters === true`.

Cookie в ответе можно игнорировать.

### 3.2. Заголовок на всех защищённых запросах

```http
Authorization: Bearer <jwt>
```

Cookie для плагина **не нужен**.

### 3.3. Срок жизни и 401

- TTL токена по умолчанию **12 часов** (`auth_token_ttl_hours`).
- **401** (`Требуется вход` / `Сессия истекла или недействительна`) → повторный login, обновить сохранённый `token`.
- Проверка сессии без повторного ввода пароля: `GET {base}/api/auth/me` с Bearer (те же поля пользователя **без** `token`).

---

## 4. Сценарий UI в плагине

```text
1. Пользователь выбирает задачу (есть task_key) и полевой отчёт (report_id).
2. GET letter-draft → заполнить форму значениями по умолчанию.
3. Пользователь правит заказчика, исполнителя, адрес, коммуникации,
   описание, признаки незаконности, выбор фото, масштаб карты.
4. (Опционально) GET map-preview при смене scale — показать PNG.
5. (Опционально) GET photos/.../image для превью в списке фото.
6. POST letters → получить fid, filename, download_url.
7. GET download_url → сохранить DOCX на диск пользователя.
```

Относительные пути (`image_url`, `download_url`) склеивайте с base URL:

```text
full = base.rstrip('/') + relative_path
```

Бинарные GET (`map-preview`, `download`, photo image) тоже отправляйте с `Authorization: Bearer`.

---

## 5. Справочник эндпоинтов

Общий префикс писем: `/api/tasks/{key}/field-reports/{report_id}/…`  
`{key}` — UUID задачи (`task_key`), URL-encode при необходимости.

### 5.1. Черновик

`GET /api/tasks/{key}/field-reports/{report_id}/letter-draft`  
`Accept: application/json`

**Ответ 200** (ключевые поля):

| Поле | Тип | Смысл |
| ---- | --- | ----- |
| `task_key`, `report_id` | str, int | эхо входа |
| `rayon`, `street`, `today`, `coordinates` | str | метаданные письма |
| `lon`, `lat` | float | центроид отчёта WGS84 |
| `incident_datetime` | str | дата фиксации (из фото) |
| `customer`, `executor`, `address`, `engineering`, `description` | str | префилл формы |
| `address_geocode`, `address_mos`, `address_has_house` | str/bool | источники адреса |
| `engineering_options` | string[] | справочник `dict.comms_full` |
| `violation_options` | string[] | справочник признаков незаконности |
| `photos[]` | объекты | `id`, `label`, `banner`, `image_url`, … |
| `map_scales`, `map_scale_default` | int[] / int | обычно `[1000,2000,5000,10000]`, default `1000` |
| `map_warning` | str\|null | предупреждение по геометрии задачи |
| `task_geometry_visibility` | str | `ok` / `partial` / `outside` / `missing` |

### 5.2. Превью ситуационного плана

`GET /api/tasks/{key}/field-reports/{report_id}/map-preview?scale={scale}`  

- `scale`: одно из `1000`, `2000`, `5000`, `10000`
- **200** `Content-Type: image/png`

### 5.3. Генерация письма

`POST /api/tasks/{key}/field-reports/{report_id}/letters`  
`Content-Type: application/json`

**Тело:**

```json
{
  "customer": "…",
  "executor": "…",
  "address": "улица, дом",
  "engineering": "не определено",
  "description": "…",
  "violation_names": ["признак из справочника", "…"],
  "photo_ids": [101, 102],
  "map_scale": 1000
}
```

| Поле | Обязательность | Заметки |
| ---- | -------------- | ------- |
| `customer`, `executor`, `address`, `engineering`, `description` | строки, могут быть пустыми | пустое description на сервере подставится дефолтом |
| `violation_names` | список | только имена из `violation_options`; иначе 422 |
| `violation` | устаревшее | многострочная строка; предпочтителен `violation_names` |
| `photo_ids` | список int | id из draft.photos; чужие id → 400 |
| `map_scale` | int | только 1000/2000/5000/10000 |

**Ответ 200:**

```json
{
  "fid": 42,
  "filename": "Письмо_….docx",
  "download_url": "/api/tasks/{key}/field-reports/{report_id}/letters/42/download"
}
```

Запись также сохраняется в `webcrm.oati_letters` (`created_by` = login сессии).

### 5.4. Скачивание DOCX

`GET /api/tasks/{key}/field-reports/{report_id}/letters/{fid}/download`

- **200** `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- имя файла — в `Content-Disposition` (`filename*` UTF-8)

Проверяется принадлежность `fid` к данной паре task/report.

### 5.5. Превью полевого фото

`GET /api/photos/field/{name}/image`  

`name` — basename из `photos[].file_path` / хвост `image_url`  
**200** — изображение (JPEG/PNG и т.п.)

### 5.6. Текущий пользователь

`GET /api/auth/me` — как login без `token`.

---

## 6. Ошибки


| HTTP | Когда | Типичный `detail` | Действие UI |
| ---- | ----- | ----------------- | ----------- |
| 401 | нет/битый token | Требуется вход… / Сессия истекла… | повторный login |
| 401 | неверный пароль | Неверный логин или пароль | показать ошибку |
| 403 | роль field и т.п. | Формирование писем недоступно… | скрыть кнопку писем |
| 404 | нет задачи/отчёта/письма | Задача не найдена / Отчёт не найден… | обновить данные из БД |
| 400 | нет геометрии отчёта; чужие photo_ids | У выбранного отчёта отсутствует геометрия / Выбранные фото… | выбрать другой отчёт / поправить photo_ids |
| 422 | неверный scale или violation_names | map_scale must be… / Недопустимые признаки… | поправить форму |


Тело ошибки FastAPI: `{ "detail": "…" }` (иногда `detail` — массив валидации).

---

## 7. Примеры

### 7.1. curl

```bash
BASE=http://172.21.198.219
TASK_KEY=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
REPORT_ID=123

TOKEN=$(curl -sS -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"login":"gena","password":"SECRET"}' | jq -r .token)

curl -sS "$BASE/api/tasks/$TASK_KEY/field-reports/$REPORT_ID/letter-draft" \
  -H "Authorization: Bearer $TOKEN" | jq .

curl -sS -X POST "$BASE/api/tasks/$TASK_KEY/field-reports/$REPORT_ID/letters" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "customer":"ООО Пример",
    "executor":"ООО Подряд",
    "address":"ул. Примерная, д. 1",
    "engineering":"не определено",
    "description":"Земляные работы без ордера",
    "violation_names":[],
    "photo_ids":[101,102],
    "map_scale":1000
  }' | tee /tmp/letter.json | jq .

DOWNLOAD=$(jq -r .download_url /tmp/letter.json)
curl -sS "$BASE$DOWNLOAD" -H "Authorization: Bearer $TOKEN" -o letter.docx
```

### 7.2. Минимальный Python (`urllib`)

```python
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class WebCrmLettersClient:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.token: str | None = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> tuple[int, bytes, str]:
        url = f"{self.base}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": accept}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, resp.read(), resp.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    def login(self, login: str, password: str) -> dict[str, Any]:
        _status, raw, _ct = self._request(
            "POST", "/api/auth/login", body={"login": login, "password": password}
        )
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("can_generate_letters"):
            raise PermissionError("can_generate_letters=false для этой роли")
        self.token = payload["token"]
        return payload

    def letter_draft(self, task_key: str, report_id: int) -> dict[str, Any]:
        path = f"/api/tasks/{task_key}/field-reports/{report_id}/letter-draft"
        _status, raw, _ct = self._request("GET", path)
        return json.loads(raw.decode("utf-8"))

    def generate_letter(
        self,
        task_key: str,
        report_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        path = f"/api/tasks/{task_key}/field-reports/{report_id}/letters"
        _status, raw, _ct = self._request("POST", path, body=payload)
        return json.loads(raw.decode("utf-8"))

    def download_letter(self, download_url: str, dest: Path) -> Path:
        path = download_url if download_url.startswith("/") else f"/{download_url}"
        _status, raw, _ct = self._request(
            "GET",
            path,
            accept="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        dest.write_bytes(raw)
        return dest


# Пример:
# client = WebCrmLettersClient("http://172.21.198.219")
# client.login("gena", "SECRET")
# draft = client.letter_draft(TASK_KEY, REPORT_ID)
# result = client.generate_letter(TASK_KEY, REPORT_ID, {
#     "customer": draft["customer"],
#     "executor": draft["executor"],
#     "address": draft["address"],
#     "engineering": draft["engineering"],
#     "description": draft["description"],
#     "violation_names": [],
#     "photo_ids": [p["id"] for p in draft["photos"]],
#     "map_scale": draft["map_scale_default"],
# })
# client.download_letter(result["download_url"], Path("letter.docx"))
```

---

## 8. Чеклист приёмки интеграции

- [ ] Login возвращает `token` и `can_generate_letters`.
- [ ] Запросы с `Authorization: Bearer` к draft/generate/download работают **без** cookie.
- [ ] Role `field` получает 403 на letter-эндпоинтах; кнопка скрыта.
- [ ] Draft подставляет адрес / заказчика / список фото и `violation_options`.
- [ ] Generate с выбранными `photo_ids` и `map_scale` сохраняет DOCX; файл открывается в Word.
- [ ] После истечения TTL повторный login восстанавливает работу (нет «залипания» старого token).
- [ ] Относительные `download_url` / `image_url` корректно склеиваются с base URL.

---

## См. также

- [qgis_module_data_contract.md](qgis_module_data_contract.md) — модель данных CRM для QGIS  
- Реализация: `backend/app/routes/letters.py`, `backend/app/letters/oati.py`  
- Роли: `backend/app/auth/session.py` → `can_generate_letters`
