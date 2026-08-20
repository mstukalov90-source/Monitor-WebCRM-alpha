"""Dataset catalog and report spec validation for Excel exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.crm.reports.errors import ReportError
from app.crm.tasks_area import AREA_STATUS_LABELS, AREA_STATUSES

MAX_SHEETS = 12
MAX_EXPORT_ROWS = 50_000
MAX_PARENT_KEYS = 8_000
SHEET_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,31}$")

NEST_RELATED = "related_sheet"
NEST_NESTED = "nested_rows"
NEST_MODES = (NEST_RELATED, NEST_NESTED)

PARENT_PREFIX_COLUMNS = ("order_key", "order_task_number", "order_rayon")

ACTION_LABELS: dict[str, str] = {
    "field_camera_survey": "Обследование камеральной задачи",
    "field_disruption_absent": "Отсутствие разрытия по задаче",
    "field_disruption_found": "Обнаружение разрытия в поле",
    "field_order_closed": "Закрытие заказа",
    "office_pre_analise_started": "Подготовка данных начата",
    "office_pre_analise_completed": "Подготовка данных завершена",
    "office_analise_started": "Анализ полевых данных начат",
    "office_analise_completed": "Анализ полевых данных завершён",
    "office_disruption_absent": "Разрытие отсутствует",
    "office_camera_tasks_created": "Создано камеральных задач",
    "office_closed_illegal": "Закрыто нелегально",
    "office_closed_legal": "Закрыто легально",
}

OBJECT_TYPE_LABELS: dict[str, str] = {
    "task": "Задача",
    "order": "Заказ",
}

ROLE_LABELS: dict[str, str] = {
    "field": "Полевые",
    "office": "Офис",
}

CLOSURE_KIND_LABELS: dict[str, str] = {
    "done_legal": "Закрыто легально",
    "done_illegal": "Закрыто нелегально",
    "clear": "Разрытие отсутствует",
}

ORDER_SCORE_LABELS: dict[str, str] = {
    "unsatisfactory": "Неудовлетворительно",
    "satisfactory": "Удовлетворительно",
    "good": "Хорошо",
}

CLOSED_TASK_SOURCES = ("done_legal", "done_illegal")
SURVEYED_TASK_SOURCES = ("done_illegal", "done_legal", "clear")

ValueType = Literal["str", "int", "float", "datetime", "bool"]
NestMode = Literal["related_sheet", "nested_rows"]


@dataclass(frozen=True)
class ColumnDef:
    id: str
    label: str
    value_type: ValueType = "str"
    format: str | None = None


@dataclass(frozen=True)
class FilterOption:
    value: str
    label: str


@dataclass(frozen=True)
class FilterDef:
    id: str
    label: str
    options: tuple[FilterOption, ...]


@dataclass(frozen=True)
class DatasetDef:
    id: str
    label: str
    description: str
    columns: tuple[ColumnDef, ...]
    filters: tuple[FilterDef, ...] = ()
    parent_datasets: tuple[str, ...] = ()

    @property
    def column_ids(self) -> frozenset[str]:
        return frozenset(col.id for col in self.columns)

    def column(self, column_id: str) -> ColumnDef:
        for col in self.columns:
            if col.id == column_id:
                return col
        raise KeyError(column_id)

    def filter_def(self, filter_id: str) -> FilterDef | None:
        for item in self.filters:
            if item.id == filter_id:
                return item
        return None


def _col(
    column_id: str,
    label: str,
    value_type: ValueType = "str",
    fmt: str | None = None,
) -> ColumnDef:
    return ColumnDef(id=column_id, label=label, value_type=value_type, format=fmt)


FIELD_SUMMARY_COLUMNS = (
    _col("user_login", "Сотрудник"),
    _col("user_role", "Роль", fmt="role"),
    _col("camera_surveys", "Обследование камеральной задачи", "int"),
    _col("disruption_absent", "Отсутствие разрытия", "int"),
    _col("disruption_found", "Обнаружение разрытия", "int"),
    _col("orders_closed", "Закрытие заказа", "int"),
    _col("orders_closed_ha", "Площадь закрытых, га", "float", "ha"),
    _col("period_from", "Период с", "datetime"),
    _col("period_to", "Период по", "datetime"),
)

OFFICE_BREAKDOWN_COLUMNS = (
    _col("user_login", "Сотрудник"),
    _col("user_role", "Роль", fmt="role"),
    _col("object_type", "Тип объекта", fmt="object_type"),
    _col("action", "Действие", fmt="action"),
    _col("action_count", "Количество", "int"),
    _col("area_hectares", "Площадь, га", "float", "ha"),
    _col("period_from", "Период с", "datetime"),
    _col("period_to", "Период по", "datetime"),
)

GEO_COLUMNS = (
    _col("okrug", "Округ"),
    _col("rayon", "Район"),
    _col("orders_closed", "Закрыто заказов", "int"),
    _col("orders_closed_ha", "Площадь закрытых, га", "float", "ha"),
    _col("orders_open", "Открыто заказов", "int"),
    _col("orders_open_ha", "Площадь открытых, га", "float", "ha"),
    _col("progress_pct", "Прогресс, %", "float", "pct"),
    _col("pre_analise_completed", "Подготовка завершена", "int"),
    _col("analise_completed", "Анализ завершён", "int"),
)

ORDER_CLOSURE_COLUMNS = (
    _col("created_at", "Дата закрытия", "datetime"),
    _col("task_number", "Номер заказа"),
    _col("rayon", "Район"),
    _col("user_login", "Сотрудник"),
    _col("area_hectares", "Площадь, га", "float", "ha"),
    _col("duration_minutes", "Длительность, мин", "int", "duration"),
    _col("object_key", "Ключ заказа"),
)

ACTION_DETAIL_COLUMNS = (
    _col("created_at", "Дата", "datetime"),
    _col("user_login", "Сотрудник"),
    _col("object_type", "Тип объекта", fmt="object_type"),
    _col("action", "Действие", fmt="action"),
    _col("task_number", "Номер / объект"),
    _col("rayon", "Район"),
    _col("area_hectares", "Площадь, га", "float", "ha"),
    _col("duration_minutes", "Длительность, мин", "int", "duration"),
    _col("object_key", "Ключ объекта"),
)

CLOSED_ORDER_COLUMNS = (
    _col("order_key", "Ключ заказа"),
    _col("task_number", "Номер заказа"),
    _col("rayon", "Район"),
    _col("status", "Статус", fmt="status"),
    _col("closed_at", "Дата закрытия", "datetime"),
    _col("closed_by", "Закрыл"),
    _col("area_hectares", "Площадь, га", "float", "ha"),
    _col("executor", "Исполнитель"),
    _col("order_score", "Оценка качества", fmt="order_score"),
)

CLOSED_TASK_COLUMNS = (
    _col("order_key", "Ключ заказа"),
    _col("order_task_number", "Номер заказа"),
    _col("order_rayon", "Район заказа"),
    _col("closure_kind", "Вид закрытия", fmt="closure_kind"),
    _col("group_name", "Группа"),
    _col("task_key", "Ключ задачи"),
    _col("sent_at", "Дата закрытия задачи", "datetime"),
    _col("is_field_data", "Полевые данные", "bool"),
    _col("is_office_task", "Камеральная задача", "bool"),
    _col("ogh_id", "ОГХ"),
    _col("oati_id", "ОАТИ"),
    _col("earthwork_id", "Земляные работы"),
    _col("localwork_id", "Местные работы"),
    _col("avr_mos_id", "АВР"),
)

SURVEYED_ORDER_SUMMARY_COLUMNS = (
    _col("order_key", "Ключ заказа"),
    _col("task_number", "Номер заказа"),
    _col("rayon", "Район"),
    _col("closed_at", "Дата обследования", "datetime"),
    _col("closed_by", "Закрыл"),
    _col("area_hectares", "Площадь, га", "float", "ha"),
    _col("pre_analise", "Подготовка завершена", "bool"),
    _col("analise", "Анализ завершён", "bool"),
    _col("tasks_surveyed", "Задач обследовано", "int"),
    _col("tasks_clear", "Разрытие отсутствует", "int"),
    _col("tasks_done_legal", "Закрыто легально", "int"),
    _col("tasks_done_illegal", "Закрыто нелегально", "int"),
    _col("tasks_open", "Ещё без исхода", "int"),
)

ACTIVE_TASK_COLUMNS = (
    _col("order_key", "Ключ заказа"),
    _col("order_task_number", "Номер заказа"),
    _col("order_rayon", "Район заказа"),
    _col("group_name", "Группа"),
    _col("task_key", "Ключ задачи"),
    _col("field_observed", "Обследовано в поле", "bool"),
    _col("is_field_data", "Полевые данные", "bool"),
    _col("is_office_task", "Камеральная задача", "bool"),
    _col("ogh_id", "ОГХ"),
    _col("oati_id", "ОАТИ"),
    _col("earthwork_id", "Земляные работы"),
    _col("localwork_id", "Местные работы"),
    _col("avr_mos_id", "АВР"),
)

STATUS_FILTER = FilterDef(
    id="status",
    label="Статус заказа",
    options=tuple(
        FilterOption(value=key, label=AREA_STATUS_LABELS[key]) for key in AREA_STATUSES
    ),
)

SOURCES_FILTER = FilterDef(
    id="sources",
    label="Источник закрытия",
    options=(
        FilterOption("done_legal", CLOSURE_KIND_LABELS["done_legal"]),
        FilterOption("done_illegal", CLOSURE_KIND_LABELS["done_illegal"]),
        FilterOption("clear", CLOSURE_KIND_LABELS["clear"]),
    ),
)

DATASETS: dict[str, DatasetDef] = {
    "field_summary": DatasetDef(
        id="field_summary",
        label="Полевые сотрудники (сводка)",
        description="Сводка действий полевых сотрудников за период.",
        columns=FIELD_SUMMARY_COLUMNS,
    ),
    "office_breakdown": DatasetDef(
        id="office_breakdown",
        label="Офис (разбивка)",
        description="Действия офиса по типу объекта и операции.",
        columns=OFFICE_BREAKDOWN_COLUMNS,
    ),
    "geo_okrugs": DatasetDef(
        id="geo_okrugs",
        label="Территория — округа",
        description="Агрегат по округам: закрытые и открытые заказы.",
        columns=GEO_COLUMNS,
    ),
    "geo_rayons": DatasetDef(
        id="geo_rayons",
        label="Территория — районы",
        description="Агрегат по районам: закрытые и открытые заказы.",
        columns=GEO_COLUMNS,
    ),
    "order_closures": DatasetDef(
        id="order_closures",
        label="Закрытия заказов (события)",
        description="Список событий field_order_closed за период.",
        columns=ORDER_CLOSURE_COLUMNS,
    ),
    "action_details": DatasetDef(
        id="action_details",
        label="Детализация сотрудника",
        description="Закрытия и этапы анализа по выбранному сотруднику.",
        columns=ACTION_DETAIL_COLUMNS,
    ),
    "closed_orders": DatasetDef(
        id="closed_orders",
        label="Закрытые заказы",
        description="Заказы из crm.tasks_area, закрытые в поле за период.",
        columns=CLOSED_ORDER_COLUMNS,
        filters=(STATUS_FILTER,),
    ),
    "closed_tasks": DatasetDef(
        id="closed_tasks",
        label="Закрытые задачи внутри заказов",
        description=(
            "Задачи из crm.tasks_done_legal / crm.tasks_done_illegal / crm.tasks_clear, "
            "геометрически внутри выбранных заказов."
        ),
        columns=CLOSED_TASK_COLUMNS,
        filters=(SOURCES_FILTER,),
        parent_datasets=("closed_orders",),
    ),
    "active_tasks_in_orders": DatasetDef(
        id="active_tasks_in_orders",
        label="Активные задачи внутри заказов",
        description="Задачи из crm.tasks, геометрически внутри выбранных заказов.",
        columns=ACTIVE_TASK_COLUMNS,
        parent_datasets=("closed_orders",),
    ),
    "surveyed_order_summary": DatasetDef(
        id="surveyed_order_summary",
        label="Обследованные заказы (сводка)",
        description=(
            "Все заказы с field_order_closed за всё время: число обследованных задач "
            "и исходы (разрытие отсутствует / легально / нелегально)."
        ),
        columns=SURVEYED_ORDER_SUMMARY_COLUMNS,
    ),
}

PRESET_CLOSED_ORDERS_WITH_TASKS_ID = "closed_orders_with_tasks"
PRESET_SURVEYED_ORDER_SUMMARY_ID = "surveyed_order_summary"


class ReportSheetSpec(BaseModel):
    id: str
    dataset: str
    title: str = ""
    columns: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    parent_sheet: str | None = None
    nest: NestMode = NEST_RELATED


class ReportSpec(BaseModel):
    name: str = "Отчёт"
    sheets: list[ReportSheetSpec] = Field(default_factory=list)


class ReportExportRequest(BaseModel):
    spec: ReportSpec
    date_from: str
    date_to: str
    user_role: str | None = None
    user_login: str | None = None
    object_type: str | None = None
    rayons: list[str] = Field(default_factory=list)


class ReportTemplateCreate(BaseModel):
    name: str
    spec: ReportSpec


class ReportTemplateUpdate(BaseModel):
    name: str | None = None
    spec: ReportSpec | None = None


def preset_closed_orders_with_tasks() -> ReportSpec:
    return ReportSpec(
        name="Закрытые заказы и задачи внутри",
        sheets=[
            ReportSheetSpec(
                id="orders",
                dataset="closed_orders",
                title="Заказы",
                columns=[
                    "task_number",
                    "rayon",
                    "status",
                    "closed_at",
                    "closed_by",
                    "area_hectares",
                    "executor",
                    "order_score",
                ],
            ),
            ReportSheetSpec(
                id="tasks",
                dataset="closed_tasks",
                title="Задачи внутри заказов",
                parent_sheet="orders",
                nest=NEST_RELATED,
                columns=[
                    "order_task_number",
                    "order_rayon",
                    "closure_kind",
                    "group_name",
                    "task_key",
                    "sent_at",
                    "oati_id",
                    "earthwork_id",
                    "ogh_id",
                ],
                filters={"sources": list(CLOSED_TASK_SOURCES)},
            ),
        ],
    )


def preset_surveyed_order_summary() -> ReportSpec:
    return ReportSpec(
        name="Обследованные заказы",
        sheets=[
            ReportSheetSpec(
                id="orders",
                dataset="surveyed_order_summary",
                title="Заказы",
                columns=[
                    "task_number",
                    "rayon",
                    "closed_at",
                    "closed_by",
                    "area_hectares",
                    "pre_analise",
                    "analise",
                    "tasks_surveyed",
                    "tasks_clear",
                    "tasks_done_legal",
                    "tasks_done_illegal",
                    "tasks_open",
                ],
            ),
        ],
    )


def _child_datasets(dataset_id: str) -> list[dict[str, str]]:
    children = []
    for item in DATASETS.values():
        if dataset_id in item.parent_datasets:
            children.append({"id": item.id, "label": item.label})
    return children


def catalog_payload() -> dict[str, Any]:
    datasets = []
    for item in DATASETS.values():
        datasets.append(
            {
                "id": item.id,
                "label": item.label,
                "description": item.description,
                "columns": [
                    {
                        "id": col.id,
                        "label": col.label,
                        "value_type": col.value_type,
                        "format": col.format,
                    }
                    for col in item.columns
                ],
                "filters": [
                    {
                        "id": flt.id,
                        "label": flt.label,
                        "type": "multi",
                        "options": [
                            {"value": opt.value, "label": opt.label} for opt in flt.options
                        ],
                    }
                    for flt in item.filters
                ],
                "parent_datasets": list(item.parent_datasets),
                "child_datasets": _child_datasets(item.id),
            }
        )
    closed_preset = preset_closed_orders_with_tasks()
    surveyed_preset = preset_surveyed_order_summary()
    return {
        "datasets": datasets,
        "presets": [
            {
                "id": PRESET_CLOSED_ORDERS_WITH_TASKS_ID,
                "name": closed_preset.name,
                "spec": closed_preset.model_dump(),
            },
            {
                "id": PRESET_SURVEYED_ORDER_SUMMARY_ID,
                "name": surveyed_preset.name,
                "spec": surveyed_preset.model_dump(),
            },
        ],
        "nest_modes": [
            {"id": NEST_RELATED, "label": "Отдельный лист"},
            {"id": NEST_NESTED, "label": "Вложенные строки"},
        ],
        "max_export_rows": MAX_EXPORT_ROWS,
    }


def resolve_sheet_columns(
    dataset: DatasetDef,
    selected: list[str],
    *,
    related_child: bool,
) -> list[ColumnDef]:
    if selected:
        unknown = [col_id for col_id in selected if col_id not in dataset.column_ids]
        if unknown:
            raise ReportError(
                f"Неизвестные колонки для «{dataset.label}»: {', '.join(unknown)}"
            )
        ordered = [dataset.column(col_id) for col_id in selected]
    else:
        ordered = list(dataset.columns)

    if not related_child:
        return ordered

    prefix_ids = [col_id for col_id in PARENT_PREFIX_COLUMNS if col_id in dataset.column_ids]
    prefix = [dataset.column(col_id) for col_id in prefix_ids]
    rest = [col for col in ordered if col.id not in prefix_ids]
    return prefix + rest


def validate_report_spec(spec: ReportSpec) -> ReportSpec:
    name = (spec.name or "").strip() or "Отчёт"
    if len(name) > 120:
        raise ReportError("Название отчёта слишком длинное")
    if not spec.sheets:
        raise ReportError("Добавьте хотя бы один лист")
    if len(spec.sheets) > MAX_SHEETS:
        raise ReportError(f"Слишком много листов (максимум {MAX_SHEETS})")

    seen_ids: set[str] = set()
    by_id: dict[str, ReportSheetSpec] = {}
    cleaned: list[ReportSheetSpec] = []

    for sheet in spec.sheets:
        sheet_id = (sheet.id or "").strip()
        if not SHEET_ID_RE.match(sheet_id):
            raise ReportError("Идентификатор листа должен начинаться с буквы (латиница, цифры, _)")
        if sheet_id in seen_ids:
            raise ReportError(f"Повторяющийся идентификатор листа: {sheet_id}")
        seen_ids.add(sheet_id)

        dataset = DATASETS.get(sheet.dataset)
        if dataset is None:
            raise ReportError(f"Неизвестный набор данных: {sheet.dataset}")

        title = (sheet.title or "").strip() or dataset.label
        if len(title) > 80:
            raise ReportError("Название листа слишком длинное")

        nest = sheet.nest if sheet.nest in NEST_MODES else NEST_RELATED
        parent_sheet = (sheet.parent_sheet or "").strip() or None
        if dataset.parent_datasets:
            if not parent_sheet:
                raise ReportError(
                    f"«{dataset.label}» нужно привязать к родительскому листу"
                )
        elif parent_sheet:
            raise ReportError(f"«{dataset.label}» не поддерживает вложенность")
        elif nest == NEST_NESTED:
            raise ReportError("Вложенные строки доступны только для связанных данных")

        filters = _validate_filters(dataset, sheet.filters)
        related_child = bool(parent_sheet) and nest == NEST_RELATED
        resolve_sheet_columns(dataset, sheet.columns, related_child=related_child)

        item = ReportSheetSpec(
            id=sheet_id,
            dataset=dataset.id,
            title=title,
            columns=list(sheet.columns),
            filters=filters,
            parent_sheet=parent_sheet,
            nest=nest,  # type: ignore[arg-type]
        )
        by_id[sheet_id] = item
        cleaned.append(item)

    for sheet in cleaned:
        if not sheet.parent_sheet:
            continue
        parent = by_id.get(sheet.parent_sheet)
        if parent is None:
            raise ReportError(f"Родительский лист «{sheet.parent_sheet}» не найден")
        dataset = DATASETS[sheet.dataset]
        if parent.dataset not in dataset.parent_datasets:
            raise ReportError(
                f"«{dataset.label}» нельзя вложить в «{DATASETS[parent.dataset].label}»"
            )
        if parent.parent_sheet:
            raise ReportError("Вложенность глубже одного уровня не поддерживается")

    return ReportSpec(name=name, sheets=cleaned)


def _validate_filters(dataset: DatasetDef, raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    allowed = {item.id: item for item in dataset.filters}
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        flt = allowed.get(key)
        if flt is None:
            raise ReportError(f"Неизвестный фильтр «{key}» для {dataset.label}")
        if value is None or value == "":
            continue
        if not isinstance(value, list):
            raise ReportError(f"Фильтр «{flt.label}» должен быть списком")
        allowed_values = {opt.value for opt in flt.options}
        picked: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            if text not in allowed_values:
                raise ReportError(f"Недопустимое значение фильтра «{flt.label}»: {text}")
            if text not in picked:
                picked.append(text)
        if picked:
            cleaned[key] = picked
    return cleaned


def format_cell_value(column: ColumnDef, value: Any) -> Any:
    if value is None:
        return None
    fmt = column.format
    if fmt == "action":
        return ACTION_LABELS.get(str(value), value)
    if fmt == "object_type":
        return OBJECT_TYPE_LABELS.get(str(value), value)
    if fmt == "role":
        return ROLE_LABELS.get(str(value), value)
    if fmt == "status":
        return AREA_STATUS_LABELS.get(str(value), value)
    if fmt == "closure_kind":
        return CLOSURE_KIND_LABELS.get(str(value), value)
    if fmt == "order_score":
        return ORDER_SCORE_LABELS.get(str(value), value)
    if column.value_type == "bool":
        if value is True:
            return "Да"
        if value is False:
            return "Нет"
        return None
    return value
