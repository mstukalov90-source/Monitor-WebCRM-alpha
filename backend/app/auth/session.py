"""User session model and role-based access constants."""

from __future__ import annotations

from dataclasses import dataclass

TaskSource = str

ALL_TASK_SOURCES: tuple[TaskSource, ...] = (
    "active",
    "field",
    "done_legal",
    "done_illegal",
    "clear",
    "area",
)

ROLE_TASK_SOURCES: dict[str, list[TaskSource]] = {
    "admin": list(ALL_TASK_SOURCES),
    "field": ["field", "area"],
    "office": ["active", "area"],
    "manager": list(ALL_TASK_SOURCES),
}

DEFAULT_TASK_SOURCE: dict[str, TaskSource] = {
    "admin": "active",
    "field": "field",
    "office": "active",
    "manager": "active",
}

ROLE_AREA_STATUSES: dict[str, list[str]] = {
    "admin": ["free", "wip", "done"],
    "field": ["wip"],
    "office": ["wip", "done"],
    "manager": ["free", "wip", "done"],
}

HOOD_SCHEMA = "odh_export"
HOOD_TABLE = "hood"
HOOD_DISPLAY_NAME = "Границы районов"


@dataclass(frozen=True)
class UserSession:
    uuid: str
    login: str
    role: str
    work_zones: list[int]


def districts_unrestricted(session: UserSession) -> bool:
    return session.role == "admin"


def allowed_task_sources(role: str) -> list[TaskSource]:
    return list(ROLE_TASK_SOURCES.get(role, []))


def default_task_source(role: str) -> TaskSource:
    return DEFAULT_TASK_SOURCE.get(role, "active")


def allowed_area_statuses(role: str) -> list[str]:
    return list(ROLE_AREA_STATUSES.get(role, []))


def can_collect(role: str) -> bool:
    return role != "field"


def can_manage_personnel(role: str) -> bool:
    return role in ("manager", "admin")


def can_create_users(role: str) -> bool:
    return role == "admin"


def hood_gid_sql_filter(session: UserSession) -> str:
    if districts_unrestricted(session) or not session.work_zones:
        return ""
    gids = ",".join(str(g) for g in session.work_zones)
    return f'"gid" IN ({gids})'


def is_hood_layer(schema: str, table: str, display_name: str) -> bool:
    return (
        schema == HOOD_SCHEMA and table == HOOD_TABLE
    ) or display_name == HOOD_DISPLAY_NAME
