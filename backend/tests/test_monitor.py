"""Tests for admin server monitor."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from app.auth.deps import require_admin
from app.auth.session import UserSession, can_view_server_monitor
from app.monitor.app_metrics import clear_metrics, record_request, snapshot_request_metrics
from app.monitor.docker_status import (
    containers_from_inspect,
    parse_mem_used_bytes,
    parse_percent,
    reset_container_seen,
)
from app.monitor.operations import clear_operations, list_operations, record_operation
from app.monitor.snapshot import clear_snapshot_cache, collect_snapshot
from app.monitor.systemd_status import parse_show_output, reset_service_seen, unit_from_props


def _session(role: str) -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login="tester",
        role=role,
        work_zones=[],
    )


class MonitorAuthTests(unittest.TestCase):
    def test_require_admin_allows_admin(self) -> None:
        user = require_admin(_session("admin"))
        self.assertEqual(user.role, "admin")

    def test_require_admin_rejects_office(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            require_admin(_session("office"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_admin_rejects_manager(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            require_admin(_session("manager"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_can_view_server_monitor_admin_only(self) -> None:
        self.assertTrue(can_view_server_monitor("admin"))
        self.assertFalse(can_view_server_monitor("manager"))
        self.assertFalse(can_view_server_monitor("office"))
        self.assertFalse(can_view_server_monitor("field"))

    def test_status_route_requires_admin(self) -> None:
        from app.auth.deps import require_admin as require_admin_dep
        from app.routes import monitor as monitor_routes

        route = next(
            r
            for r in monitor_routes.router.routes
            if getattr(r, "path", None) == "/api/monitor/status"
        )
        dependant = route.dependant
        dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
        self.assertIn(require_admin_dep, dep_calls)


class OperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operations()

    def tearDown(self) -> None:
        clear_operations()

    def test_list_newest_first(self) -> None:
        record_operation("first", "ok", "one")
        record_operation("second", "warn", "two")
        items = list_operations()
        self.assertEqual([item["name"] for item in items], ["second", "first"])
        self.assertEqual(items[0]["status"], "warn")
        self.assertEqual(items[0]["detail"], "two")
        self.assertIn("ts", items[0])


class AppMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_metrics()

    def tearDown(self) -> None:
        clear_metrics()

    def test_requests_per_minute_and_p95(self) -> None:
        for ms in (10.0, 20.0, 30.0, 40.0, 100.0):
            record_request(ms)
        snap = snapshot_request_metrics()
        self.assertEqual(snap["requests_per_minute"], 5)
        self.assertEqual(snap["p95_ms"], 100.0)


class DockerParseTests(unittest.TestCase):
    def test_parse_percent_and_mem(self) -> None:
        self.assertEqual(parse_percent("12.50%"), 12.5)
        self.assertEqual(parse_mem_used_bytes("4.1GiB / 8GiB"), int(4.1 * 1024**3))

    def test_containers_from_inspect(self) -> None:
        started = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        payload = [
            {
                "Name": "/monitor-db",
                "State": {
                    "Status": "running",
                    "StartedAt": started,
                    "RestartCount": 1,
                    "Health": {"Status": "healthy"},
                },
            },
            {
                "Name": "/stopped",
                "State": {
                    "Status": "exited",
                    "StartedAt": started,
                    "RestartCount": 0,
                },
            },
        ]
        stats = {"monitor-db": {"CPUPerc": "3.20%", "MemUsage": "220MiB / 2GiB"}}
        units = containers_from_inspect(payload, stats)
        by_name = {u["name"]: u for u in units}
        self.assertEqual(by_name["monitor-db"]["kind"], "docker")
        self.assertEqual(by_name["monitor-db"]["level"], "ok")
        self.assertEqual(by_name["monitor-db"]["cpu_percent"], 3.2)
        self.assertEqual(by_name["stopped"]["level"], "error")
        self.assertIsNone(by_name["stopped"]["uptime_seconds"])


class SystemdParseTests(unittest.TestCase):
    def test_unit_from_props_active(self) -> None:
        raw = "\n".join(
            [
                "Id=monitor-webcrm.service",
                "ActiveState=active",
                "SubState=running",
                "NRestarts=0",
                "MemoryCurrent=188743680",
            ]
        )
        unit = unit_from_props("monitor-webcrm", parse_show_output(raw))
        self.assertEqual(unit["level"], "ok")
        self.assertEqual(unit["kind"], "systemd")
        self.assertEqual(unit["memory_bytes"], 188743680)
        self.assertEqual(unit["health"], "running")

    def test_unit_from_props_inactive(self) -> None:
        unit = unit_from_props("nginx", {"ActiveState": "inactive", "SubState": "dead"})
        self.assertEqual(unit["level"], "error")


class SnapshotDegradationTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_snapshot_cache()
        clear_operations()
        reset_container_seen()
        reset_service_seen()

    def tearDown(self) -> None:
        clear_snapshot_cache()
        clear_operations()
        reset_container_seen()
        reset_service_seen()

    @patch(
        "app.monitor.snapshot.list_docker_containers",
        return_value=([], "команда docker не найдена"),
    )
    @patch(
        "app.monitor.snapshot.list_systemd_units",
        return_value=([], "команда systemctl не найдена"),
    )
    @patch("app.monitor.snapshot._database_metrics", return_value=None)
    def test_snapshot_without_docker(
        self,
        _db_mock: object,
        _sys_mock: object,
        _docker_mock: object,
    ) -> None:
        snap = collect_snapshot()
        self.assertEqual(snap["units"], [])
        self.assertTrue(any("Docker" in w for w in snap["warnings"]))
        self.assertTrue(any("systemd" in w for w in snap["warnings"]))
        self.assertIn("collected_at", snap)
        self.assertIn(snap["overall"], ("ok", "warn", "error"))
        self.assertIsNotNone(snap["app"])
        self.assertEqual(snap["operations"], [])


class CollectOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operations()

    def tearDown(self) -> None:
        clear_operations()

    def test_record_collect_result(self) -> None:
        from app.crm.collector import TaskResult, _record_collect_result

        result = TaskResult(
            district_name="Аэропорт",
            filter_date_from=datetime.now().date(),
            filter_date_to=datetime.now().date(),
            errors=["layer missing"],
        )
        _record_collect_result("Аэропорт", result)
        items = list_operations()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "collect «Аэропорт»")
        self.assertEqual(items[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
