"""Pydantic schemas for CRM API."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class CollectTasksRequest(BaseModel):
    rayon: str
    apply_date_filter: bool = True


class CollectLayerRequest(BaseModel):
    rayon: str
    apply_date_filter: bool = True
    group_name: str
    subgroup_name: str
    layer_key: str


class CollectPlanLayerOut(BaseModel):
    group_name: str
    subgroup_name: str
    layer_key: str
    layer_name: str


class CollectPlanOut(BaseModel):
    district_name: str
    filter_date_from: date
    filter_date_to: date
    apply_date_filter: bool = True
    groups: list[TaskGroupOut] = Field(default_factory=list)
    layers: list[CollectPlanLayerOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CollectLayerOut(BaseModel):
    group_name: str
    subgroup_name: str
    layer_key: str
    features: list[TaskFeatureOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TaskFeatureOut(BaseModel):
    layer_name: str
    layer_key: str
    attributes: dict[str, Any]
    geometry: dict[str, Any] | None = None


class TaskSubgroupOut(BaseModel):
    name: str
    date_field: str | None = None
    features: list[TaskFeatureOut] = Field(default_factory=list)


class TaskGroupOut(BaseModel):
    name: str
    subgroups: list[TaskSubgroupOut] = Field(default_factory=list)


class PersistStatsOut(BaseModel):
    inserted: int = 0
    skipped: int = 0
    invalid: int = 0


class TaskResultOut(BaseModel):
    district_name: str
    filter_date_from: date
    filter_date_to: date
    apply_date_filter: bool = True
    groups: list[TaskGroupOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    persist_stats: PersistStatsOut | None = None

    @property
    def total_count(self) -> int:
        return sum(len(s.features) for g in self.groups for s in g.subgroups)


class TaskRecordOut(BaseModel):
    key: str
    type: str
    photo_uuid: str | None = None
    photo_lens: str | None = None
    ogh_id: str | None = None
    oati_id: str | None = None
    earthwork_id: str | None = None
    localwork_id: str | None = None
    avr_mos_id: str | None = None
    sps: str | None = None
    kgs: str | None = None
    station_avr: str | None = None


class TaskRecordUpdate(BaseModel):
    type: str | None = None
    photo_uuid: str | None = None
    photo_lens: str | None = None
    ogh_id: str | None = None
    oati_id: str | None = None
    earthwork_id: str | None = None
    localwork_id: str | None = None
    avr_mos_id: str | None = None
    sps: str | None = None
    kgs: str | None = None
    station_avr: str | None = None


class TaskFormFieldsOut(BaseModel):
    readonly_fields: list[str]
    link_fields: list[str]
    labels: dict[str, str]


class SnapshotResultOut(BaseModel):
    status: str
