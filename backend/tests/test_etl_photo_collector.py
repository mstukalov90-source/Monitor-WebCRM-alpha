"""Tests for ETL-synced photo task loading (no map collectors)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.crm.collector import build_collect_plan, persist_district_tasks
from app.crm.etl_photo_loader import (
    AI_PHOTO_SUBGROUP,
    LENS_PHOTO_SUBGROUP,
    is_etl_sync_subgroup,
)


class EtlPhotoCollectorPlanTests(unittest.TestCase):
    def test_photo_subgroups_marked_etl_sync(self) -> None:
        from app.config import crm_tasks_config

        cfg = crm_tasks_config()
        for group in cfg.get("groups", []):
            for sub in group.get("subgroups", []):
                if sub.get("source") == "etl_sync":
                    self.assertTrue(is_etl_sync_subgroup(sub["name"], cfg))

    def test_build_collect_plan_excludes_etl_layers_from_plan(self) -> None:
        from app.config import crm_tasks_config

        cfg = crm_tasks_config()
        etl_names = [
            sub["name"]
            for group in cfg.get("groups", [])
            for sub in group.get("subgroups", [])
            if sub.get("source") == "etl_sync"
        ]
        self.assertGreaterEqual(len(etl_names), 2)

        result, layers = build_collect_plan("Сокол", apply_date_filter=True)
        layer_subgroup_names = {item.subgroup_name for item in layers}
        for name in etl_names:
            self.assertNotIn(name, layer_subgroup_names)

        subgroup_names = {
            subgroup.name
            for group in result.groups
            for subgroup in group.subgroups
        }
        for name in etl_names:
            self.assertIn(name, subgroup_names)

    @patch("app.crm.collector.fetch_district_wkt", return_value="POLYGON((0 0,1 0,1 1,0 1,0 0))")
    @patch("app.crm.collector.release_persist_rayon_lock")
    @patch("app.crm.collector.acquire_persist_rayon_lock", return_value=1)
    @patch("app.crm.collector.persist_new_tasks_in_district")
    def test_persist_district_tasks_skips_etl_sync(
        self,
        persist_mock: MagicMock,
        _lock: MagicMock,
        _release: MagicMock,
        _wkt: MagicMock,
    ) -> None:
        from app.config import crm_tasks_config

        cfg = crm_tasks_config()
        etl_names = {
            sub["name"]
            for group in cfg.get("groups", [])
            for sub in group.get("subgroups", [])
            if sub.get("source") == "etl_sync"
        }
        conn = MagicMock()
        persist_district_tasks(conn, "Сокол", apply_date_filter=True, login="test")
        called_subgroups = {call.args[2] for call in persist_mock.call_args_list}
        self.assertTrue(etl_names.isdisjoint(called_subgroups))


class EtlPhotoLoaderSqlTests(unittest.TestCase):
    @patch("app.crm.etl_photo_loader.fetch_snapshot_task_keys", return_value=set())
    @patch("app.crm.etl_photo_loader.fetch_task_attributes_in_district")
    @patch("app.crm.etl_photo_loader._district_context")
    @patch("app.crm.etl_photo_loader.crm_task_store_config")
    @patch("app.crm.etl_photo_loader.crm_tasks_config")
    def test_collect_etl_sync_delegates_to_join_loader(
        self,
        cfg_mock: MagicMock,
        store_mock: MagicMock,
        district_mock: MagicMock,
        fetch_mock: MagicMock,
        _snap_mock: MagicMock,
    ) -> None:
        from app.crm.etl_photo_loader import collect_etl_sync_subgroup_tasks

        district_mock.return_value = ("POLYGON()", 32637, [])
        store_mock.return_value = {
            "schema": "crm",
            "table": "tasks",
            "subgroups": {
                AI_PHOTO_SUBGROUP: {
                    "task_column": "photo_uuid",
                    "source_field": "uuid",
                }
            },
        }
        cfg_mock.return_value = {
            "groups": [
                {
                    "name": "Разрытия",
                    "subgroups": [
                        {
                            "name": AI_PHOTO_SUBGROUP,
                            "source": "etl_sync",
                            "layers": ["Фотографии после обработки ИИ"],
                        }
                    ],
                }
            ],
        }
        fetch_mock.return_value = [
            {
                "layer_name": "Фотографии после обработки ИИ",
                "layer_key": "фотографии_после_обработки_ии",
                "attributes": {"uuid": "abc"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "task_key": "task-1",
            }
        ]

        features, errors = collect_etl_sync_subgroup_tasks(
            MagicMock(), "Сокол", AI_PHOTO_SUBGROUP, apply_date_filter=True
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0].task_key, "task-1")
        fetch_mock.assert_called()


if __name__ == "__main__":
    unittest.main()
