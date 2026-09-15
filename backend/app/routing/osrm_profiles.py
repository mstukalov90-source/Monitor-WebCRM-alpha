"""Canonical OSRM profiles and export filename letters (А / В / П)."""

from __future__ import annotations

from urllib.parse import quote

CANONICAL_PROFILES = ("driving", "bicycle", "foot")

# API / UI aliases → OSRM path profile (must match the docker instance).
_ALIASES: dict[str, str] = {
    "driving": "driving",
    "car": "driving",
    "a": "driving",
    "а": "driving",
    "bicycle": "bicycle",
    "bike": "bicycle",
    "cycling": "bicycle",
    "v": "bicycle",
    "в": "bicycle",
    "foot": "foot",
    "walking": "foot",
    "walk": "foot",
    "p": "foot",
    "п": "foot",
}

# Cyrillic letters in download names: А auto, В bike, П pedestrian.
FILE_LETTER: dict[str, str] = {
    "driving": "А",
    "bicycle": "В",
    "foot": "П",
}
FILE_LETTER_ASCII: dict[str, str] = {
    "driving": "A",
    "bicycle": "V",
    "foot": "P",
}
NETWORK_ADJECTIVE: dict[str, str] = {
    "driving": "автомобильной",
    "bicycle": "велосипедной",
    "foot": "пешеходной",
}


class UnknownOsrmProfile(ValueError):
    pass


def canonicalize_osrm_profile(profile: str | None) -> str:
    raw = (profile or "foot").strip()
    mapped = _ALIASES.get(raw.casefold())
    if mapped is None:
        raise UnknownOsrmProfile(
            "Неизвестный граф маршрута: укажите driving (А), bicycle (В) или foot (П)"
        )
    return mapped


def profile_from_params(params: object) -> str:
    if isinstance(params, dict):
        try:
            return canonicalize_osrm_profile(str(params.get("profile") or "foot"))
        except UnknownOsrmProfile:
            return "foot"
    return "foot"


def _safe_order_stem(task_number: str | None, order_key: str) -> str:
    stem = (task_number or "").strip()
    for ch in '\\/:*?"<>|\r\n\t':
        stem = stem.replace(ch, "_")
    stem = " ".join(stem.split())
    if not stem:
        stem = (order_key or "route")[:8]
    return stem[:80]


def route_export_names(
    task_number: str | None,
    order_key: str,
    profile: str,
    ext: str,
) -> tuple[str, str]:
    """Return (ascii_filename, utf8_filename) like ``12345_П.gpx``."""
    canon = canonicalize_osrm_profile(profile)
    stem = _safe_order_stem(task_number, order_key)
    ascii_stem = stem.encode("ascii", "ignore").decode("ascii").strip("._ ") or (
        order_key or "route"
    )[:8]
    utf_name = f"{stem}_{FILE_LETTER[canon]}.{ext}"
    ascii_name = f"{ascii_stem}_{FILE_LETTER_ASCII[canon]}.{ext}"
    return ascii_name, utf_name


def route_content_disposition(
    task_number: str | None,
    order_key: str,
    profile: str,
    ext: str,
) -> str:
    ascii_name, utf_name = route_export_names(task_number, order_key, profile, ext)
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(utf_name)}'
