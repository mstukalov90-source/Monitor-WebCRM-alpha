"""Парсинг дат из атрибутов (как в QGIS crm_tasks.py)."""

from __future__ import annotations

from datetime import date, datetime

_DATE_TEXT_FORMATS = (
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def parse_attribute_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    candidates = [text]
    if len(text) >= 10:
        candidates.append(text[:10])
    if len(text) >= 19:
        candidates.append(text[:19])

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        for fmt in _DATE_TEXT_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def attribute_matches_date_range(
    attributes: dict,
    field_name: str,
    date_from: date,
    date_to: date,
) -> bool:
    if field_name not in attributes:
        return False
    feat_date = parse_attribute_date(attributes.get(field_name))
    if feat_date is None:
        return False
    return date_from <= feat_date <= date_to
