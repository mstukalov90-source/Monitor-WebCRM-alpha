"""Pydantic schemas for CRM API."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CollectTasksRequest(BaseModel):
    rayon: str
    apply_date_filter: bool = False


class CollectLayerRequest(BaseModel):
    rayon: str
    apply_date_filter: bool = False
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
    apply_date_filter: bool = False
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
    apply_date_filter: bool = False
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
    field_observed: bool | None = None
    is_field_data: bool | None = None
    is_office_task: bool | None = None
    user_created: list[str] | None = None
    user_last_edit: list[str] | None = None


class CreateOfficeTaskRequest(BaseModel):
    geometry: dict[str, Any]
    area_task_key: str | None = None
    link_prefill: dict[str, str] | None = None


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


class SendToFieldRequest(BaseModel):
    rayon: str
    office_comment: str | None = None


class SnapshotActionRequest(BaseModel):
    rayon: str | None = None


class PostponeTaskRequest(BaseModel):
    delay_until: date
    rayon: str | None = None


class PersonnelUserOut(BaseModel):
    uuid: str
    login: str
    name: str
    role: str
    work_zones: list[int]
    district_names: list[str]


class PersonnelUserUpdate(BaseModel):
    work_zones: list[int]


class PersonnelUserCreate(BaseModel):
    login: str
    name: str
    password: str
    role: str
    work_zones: list[int] = Field(default_factory=list)


class DistrictOptionOut(BaseModel):
    gid: int
    rayon: str


class AssignableTaskOut(BaseModel):
    key: str
    table: str
    executor: str | None = None
    type: str | None = None
    task_key: str | None = None
    sent_at: str | None = None
    rayon: str | None = None
    status: str | None = None
    area: float | None = None
    date_survey: str | None = None
    task_number: str | None = None


class TaskExecutorUpdate(BaseModel):
    executor: str | None = None


class TaskNumberUpdate(BaseModel):
    task_number: str | None = None


class BulkAssignRequest(BaseModel):
    table: str
    keys: list[str]
    executor: str | None = None


class BulkAssignResultOut(BaseModel):
    updated: int
    not_found: int


class BulkStatusRequest(BaseModel):
    task_keys: list[str]
    target_status: str
    rayon: str | None = None


class BulkStatusFailureOut(BaseModel):
    task_key: str
    error: str


class BulkStatusResultOut(BaseModel):
    updated: int
    skipped: int
    not_found: int
    failed: list[BulkStatusFailureOut]


class FieldSnapshotLookupOut(BaseModel):
    snapshot_key: str
    executor: str | None = None


class FieldPhotoOut(BaseModel):
    id: int
    file_path: str
    banner: bool
    created_at: str | None = None
    taken_at: str | None = None
    photo_key: str | None = None
    username: str | None = None
    label: str | None = None
    image_url: str


class FieldPhotosResultOut(BaseModel):
    photos: list[FieldPhotoOut] = Field(default_factory=list)
    banner_missing: bool = False
    comment: str | None = None


class FieldReportOut(BaseModel):
    report_id: int
    report_task: str | None = None
    geometry: dict[str, Any]
    attributes: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None
    photo_key: str | None = None


class FieldReportsResultOut(BaseModel):
    reports: list[FieldReportOut] = Field(default_factory=list)


class FieldStatisticsSummaryOut(BaseModel):
    user_login: str
    user_role: str
    camera_surveys: int
    disruption_absent: int
    disruption_found: int
    orders_closed: int
    orders_closed_ha: float = 0.0
    period_from: str | None = None
    period_to: str | None = None


class OfficeStatisticsBreakdownOut(BaseModel):
    user_login: str
    user_role: str
    object_type: str
    action: str
    action_count: int
    area_hectares: float = 0.0
    period_from: str | None = None
    period_to: str | None = None


class StatisticsActionDetailOut(BaseModel):
    user_login: str
    user_role: str
    object_type: str
    action: str
    object_key: str
    created_at: str
    task_number: str | None = None
    rayon: str | None = None
    area_hectares: float = 0.0
    duration_minutes: int | None = None
    order_score: FieldScoreValue | None = None


class PersonnelStatisticsOut(BaseModel):
    field_summary: list[FieldStatisticsSummaryOut] = Field(default_factory=list)
    office_breakdown: list[OfficeStatisticsBreakdownOut] = Field(default_factory=list)
    action_details: list[StatisticsActionDetailOut] = Field(default_factory=list)
    date_from: str
    date_to: str
    scope: Literal["all", "self"] = "all"


class GeoStatisticsRowOut(BaseModel):
    okrug: str | None = None
    rayon: str | None = None
    orders_closed: int = 0
    orders_closed_ha: float = 0.0
    orders_open: int = 0
    orders_open_ha: float = 0.0
    pre_analise_completed: int = 0
    analise_completed: int = 0
    progress_pct: float | None = None


class GeoStatisticsOut(BaseModel):
    okrugs: list[GeoStatisticsRowOut] = Field(default_factory=list)
    rayons: list[GeoStatisticsRowOut] = Field(default_factory=list)
    date_from: str
    date_to: str


class OrderClosuresStatisticsOut(BaseModel):
    closures: list[StatisticsActionDetailOut] = Field(default_factory=list)
    date_from: str
    date_to: str


class OrderStatusFeedOut(BaseModel):
    events: list[StatisticsActionDetailOut] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    date_from: str
    date_to: str


class TaskViewFeatureOut(BaseModel):
    layer_name: str
    layer_key: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    task_key: str | None = None


class TaskViewContextOut(BaseModel):
    task_key: str
    group_name: str
    subgroup_name: str
    feature: TaskViewFeatureOut


class TaskGroupMapFeatureOut(BaseModel):
    task_key: str
    subgroup_name: str = ""
    source: str = "active"
    layer_name: str = ""
    layer_key: str = ""
    geometry: dict[str, Any] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TaskGroupMapOut(BaseModel):
    rayon: str = ""
    group_name: str = ""
    selected_task_key: str
    features: list[TaskGroupMapFeatureOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OrderSearchHitOut(BaseModel):
    subgroup_name: str
    layer_name: str
    layer_key: str
    task_key: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    in_selected_rayon: bool = False


class OrderSearchResultOut(BaseModel):
    query: str
    rayon: str = ""
    hits: list[OrderSearchHitOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OrderTrackOut(BaseModel):
    id: str
    attributes: dict[str, Any]
    geometry: dict[str, Any]


class OrderTracksResultOut(BaseModel):
    district_name: str
    tracks: list[OrderTrackOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


FieldScoreValue = Literal["unsatisfactory", "satisfactory", "good"]


class FieldScoreOrderOut(BaseModel):
    order_key: str
    task_number: str | None = None
    rayon: str | None = None
    area: float | None = None
    status: str | None = None
    date_survey: str | None = None
    geometry: dict[str, Any] | None = None


class FieldScoreTaskOut(BaseModel):
    task_key: str
    report_id: int | None = None
    source: str
    group_name: str = ""
    subgroup_name: str = ""
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    sent_at: str | None = None


class FieldScoreTrackOut(BaseModel):
    id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any]
    buffer_geometry: dict[str, Any] | None = None


class FieldScoreSavedOut(BaseModel):
    order_key: str
    task_scores: dict[str, FieldScoreValue] = Field(default_factory=dict)
    track_coverage_pct: float | None = None
    order_score: FieldScoreValue | None = None
    scored_by: str
    scored_at: str | None = None
    updated_at: str | None = None
    coverage_hint: FieldScoreValue | None = None


class FieldScoreContextOut(BaseModel):
    order: FieldScoreOrderOut
    tasks: list[FieldScoreTaskOut] = Field(default_factory=list)
    tracks: list[FieldScoreTrackOut] = Field(default_factory=list)
    track_coverage_pct: float | None = None
    coverage_hint: FieldScoreValue | None = None
    buffer_meters: float = 50.0
    saved: FieldScoreSavedOut | None = None
    errors: list[str] = Field(default_factory=list)


class FieldScoreUpsertRequest(BaseModel):
    task_scores: dict[str, FieldScoreValue] = Field(default_factory=dict)
    order_score: FieldScoreValue | None = None


class OznMatchOrderOut(BaseModel):
    order_key: str
    task_number: str | None = None
    rayon: str | None = None
    area: float | None = None
    status: str | None = None
    executor: str | None = None
    match_count: int
    geometry: dict[str, Any]


class OznMatchObjectOut(BaseModel):
    id: str
    label: str
    order_name: str | None = None
    ozn_date: str | None = None
    executor: str | None = None
    geometry: dict[str, Any]


class OznMatchResultOut(BaseModel):
    district_name: str
    orders: list[OznMatchOrderOut] = Field(default_factory=list)
    ozn_objects: list[OznMatchObjectOut] = Field(default_factory=list)
    matches: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class EmployeeLocationOut(BaseModel):
    id: str
    attributes: dict[str, Any]
    geometry: dict[str, Any]


class EmployeeLocationsResultOut(BaseModel):
    district_name: str
    locations: list[EmployeeLocationOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OatiLetterPhotoOut(BaseModel):
    id: int
    file_path: str
    banner: bool = False
    created_at: str | None = None
    label: str | None = None
    image_url: str


class OatiLetterDraftOut(BaseModel):
    task_key: str
    report_id: int
    rayon: str = ""
    street: str = ""
    today: str = ""
    coordinates: str = ""
    lon: float
    lat: float
    incident_datetime: str = ""
    customer: str = ""
    executor: str = ""
    address: str = ""
    engineering: str = ""
    description: str = ""
    violation: str = ""
    photos: list[OatiLetterPhotoOut] = Field(default_factory=list)
    map_warning: str | None = None
    task_geometry_visibility: str = "missing"
    address_auto: bool = False
    address_has_house: bool = False
    address_geocode: str = ""
    address_mos: str = ""
    engineering_options: list[str] = Field(default_factory=list)
    violation_options: list[str] = Field(default_factory=list)
    map_scales: list[int] = Field(default_factory=lambda: [1000, 2000, 5000, 10000])
    map_scale_default: int = 1000


class OatiLetterGenerateRequest(BaseModel):
    customer: str = ""
    executor: str = ""
    address: str = ""
    engineering: str = ""
    description: str = ""
    violation: str = ""
    violation_names: list[str] = Field(default_factory=list)
    photo_ids: list[int] = Field(default_factory=list)
    map_scale: int = 1000

    @field_validator("map_scale")
    @classmethod
    def _validate_map_scale(cls, value: int) -> int:
        allowed = {1000, 2000, 5000, 10000}
        if value not in allowed:
            raise ValueError(f"map_scale must be one of {sorted(allowed)}")
        return value


class OatiLetterGenerateOut(BaseModel):
    fid: int
    filename: str
    download_url: str
