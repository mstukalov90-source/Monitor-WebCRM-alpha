"""Auth for order-route API: field, manager, admin."""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.auth.deps import require_order_route_access
from app.auth.session import UserSession


def _session(role: str) -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login="tester",
        role=role,
        work_zones=[1],
    )


class OrderRouteAccessTests(unittest.TestCase):
    def test_allows_field_manager_admin(self) -> None:
        for role in ("field", "manager", "admin"):
            self.assertEqual(require_order_route_access(_session(role)).role, role)

    def test_rejects_office(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            require_order_route_access(_session("office"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_route_endpoints_use_order_route_access(self) -> None:
        from app.routes import order_routes as order_route_mod

        paths = {
            "/api/crm/tasks-area/{key}/build-route",
            "/api/crm/tasks-area/{key}/route",
            "/api/crm/tasks-area/{key}/route.gpx",
            "/api/crm/tasks-area/{key}/route.geojson",
        }
        found: set[str] = set()
        for route in order_route_mod.router.routes:
            path = getattr(route, "path", None)
            if path not in paths:
                continue
            found.add(path)
            dependant = route.dependant
            dep_calls = [d.call for d in dependant.dependencies if d.call is not None]
            self.assertIn(require_order_route_access, dep_calls)
        self.assertEqual(found, paths)
