"""Build restore SQL plans and apply them through a RestoreClient."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

from app.crm.store import CRM_GROUP_DISRUPTIONS
from app.field_zip_restore.parse import (
    MOSCOW,
    DrawSubmission,
    FieldZipArchive,
    company_from_features,
    event_comment,
    format_duration,
    is_junk_track,
    ms_to_datetime,
    photo_uuid_for,
    primary_photo,
    should_skip_area_close,
    taken_at_from_name,
)


class RestoreClient(Protocol):
    def psql(self, sql: str) -> str: ...

    def psql_json(self, sql: str) -> Any: ...

    def copy_photos(self, files: list[tuple[str, bytes, int]], dest_dir: str) -> None: ...

    def apply_sql(self, statements: list[str]) -> None: ...


def sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def sql_ts(stamp: datetime | None) -> str:
    if stamp is None:
        return "NULL"
    iso = stamp.astimezone(timezone.utc).isoformat()
    return f"TIMESTAMPTZ '{iso.replace(chr(39), chr(39) * 2)}'"


def sql_geom_point(lon: float, lat: float) -> str:
    geo = json.dumps({"type": "Point", "coordinates": [lon, lat]}, separators=(",", ":"))
    return f"ST_SetSRID(ST_GeomFromGeoJSON({sql_str(geo)}), 4326)"


def sql_geom_line(points: Sequence[tuple[float, float]]) -> str:
    geo = json.dumps({"type": "LineString", "coordinates": [list(p) for p in points]}, separators=(",", ":"))
    return f"ST_SetSRID(ST_GeomFromGeoJSON({sql_str(geo)}), 4326)"


def sql_bool(value: bool) -> str:
    return "TRUE" if value else "FALSE"


@dataclass
class PlannedPhoto:
    uuid: str
    file_name: str
    zip_path: str
    slot: str
    task: str
    taken_at: datetime | None
    banner: bool


@dataclass
class RestorePlan:
    archive: FieldZipArchive
    actions: list[str]
    photos: list[PlannedPhoto]
    sql_statements: list[str]
    skip_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    field_key: str | None = None
    tasks_key: str | None = None
    area_status: str | None = None
    original_name: str | None = None
    is_field_data_close: bool = False

    @property
    def will_write(self) -> bool:
        return bool(self.sql_statements)

    @property
    def outcome(self) -> str:
        if self.will_write:
            return "ok"
        reason = (self.skip_reason or "").lower()
        if "not found" in reason:
            return "mismatch"
        return "skip"

    @property
    def close_kind(self) -> str | None:
        if self.archive.kind == "area":
            if any("wip_field → done" in action for action in self.actions):
                return "area_done"
            if self.will_write and any("insert track" in action for action in self.actions):
                return "track_only"
            return None
        if not self.archive.submissions:
            return None
        if self.is_field_data_close:
            return "field_data"
        return "clear" if self.archive.as_clear else "observed"


def planned_photos_for_submission(
    archive: FieldZipArchive,
    submission: DrawSubmission,
) -> list[PlannedPhoto]:
    fallback = ms_to_datetime(submission.created_at_ms) or archive.exported_at
    result: list[PlannedPhoto] = []
    seen: set[str] = set()
    for photo in submission.photos:
        if photo.zip_path in seen:
            continue
        seen.add(photo.zip_path)
        photo_id = photo_uuid_for(archive.path.stem, photo.zip_path)
        ext = Path(photo.zip_path).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png"}:
            ext = ".jpg"
        result.append(
            PlannedPhoto(
                uuid=photo_id,
                file_name=f"{photo_id}{ext}",
                zip_path=photo.zip_path,
                slot=photo.slot,
                task=submission.id,
                taken_at=taken_at_from_name(photo.zip_path, fallback),
                banner=photo.slot == "BANNER",
            )
        )
    return result


def photo_insert_sql(photo: PlannedPhoto, username: str) -> str:
    return f"""
INSERT INTO mggt_field.photos (
    task, file_path, photo_key, username, banner, banner_number,
    company_matches, taken_at, object_type, created_at
)
VALUES (
    {sql_str(photo.task)},
    {sql_str(photo.file_name)},
    {sql_str(photo.uuid)},
    {sql_str(username)},
    {sql_bool(photo.banner)},
    FALSE,
    FALSE,
    {sql_ts(photo.taken_at)},
    NULL,
    {sql_ts(photo.taken_at)}
)
ON CONFLICT (photo_key) WHERE photo_key IS NOT NULL DO UPDATE SET
    task = EXCLUDED.task,
    file_path = EXCLUDED.file_path,
    username = EXCLUDED.username,
    banner = EXCLUDED.banner,
    taken_at = COALESCE(EXCLUDED.taken_at, mggt_field.photos.taken_at)
""".strip()


def report_insert_sql(
    *,
    submission: DrawSubmission,
    tasks_key: str,
    username: str,
    company: str | None,
    photo_uuid: str | None,
    created_at: datetime | None,
    banner: bool,
) -> str:
    return f"""
INSERT INTO mggt_field.reports (
    task, tasks_key, point, line, comment, photo, username,
    banner, banner_number, company, company_matches, comm_type, created_at
)
VALUES (
    {sql_str(submission.id)},
    {sql_str(tasks_key)}::uuid,
    {sql_geom_point(submission.lon, submission.lat)},
    NULL,
    {sql_str(event_comment(submission))},
    {sql_str(photo_uuid)},
    {sql_str(username)},
    {sql_bool(banner)},
    FALSE,
    {sql_str(company)},
    FALSE,
    NULL,
    {sql_ts(created_at)}
)
""".strip()


def field_disruption_absent_sql(tasks_key: str, username: str, created_at: datetime | None) -> str:
    """Clear-trigger 5-min window misses historical report timestamps; emit the field event explicitly."""
    return f"""
SELECT crm.statistics_emit_field_event(
    'field_disruption_absent',
    {sql_str(tasks_key)}::uuid,
    {sql_str(username)},
    {sql_ts(created_at)},
    jsonb_build_object('source', 'restore_field_zips', 'via', 'tasks_clear_insert')
)
""".strip()


def field_disruption_found_sql(tasks_key: str, username: str, created_at: datetime | None) -> str:
    """Insert-trigger 5-min window misses historical report timestamps; emit the field event explicitly."""
    return f"""
SELECT crm.statistics_emit_field_event(
    'field_disruption_found',
    {sql_str(tasks_key)}::uuid,
    {sql_str(username)},
    {sql_ts(created_at)},
    jsonb_build_object('source', 'restore_field_zips', 'via', 'field_data_insert')
)
""".strip()


def _user_audit_array_sql(username: str) -> str:
    user_sql = sql_str(username)
    return (
        f"ARRAY[{user_sql}, to_char(NOW() AT TIME ZONE 'UTC', "
        f"'YYYY-MM-DD\"T\"HH24:MI:SS.US') || '+00:00']"
    )


def insert_field_data_task_sql(tasks_key: str, username: str) -> str:
    audit = _user_audit_array_sql(username)
    return f"""
INSERT INTO crm.tasks (
    key, type, field_observed, is_field_data, is_office_task,
    user_created, user_last_edit
) VALUES (
    {sql_str(tasks_key)}::uuid,
    {sql_str(CRM_GROUP_DISRUPTIONS)},
    TRUE,
    TRUE,
    FALSE,
    {audit},
    {audit}
)
ON CONFLICT (key) DO UPDATE SET
    is_field_data = TRUE,
    field_observed = TRUE,
    user_last_edit = EXCLUDED.user_last_edit
""".strip()


def complete_as_clear_sql(
    field_key: str,
    tasks_key: str,
    username: str,
    created_at: datetime | None,
) -> list[str]:
    user_sql = sql_str(username)
    return [
        f"""
INSERT INTO crm.tasks_clear (
    key, task_key, type, photo_uuid, photo_lens, ogh_id, oati_id,
    earthwork_id, localwork_id, avr_mos_id, sps, kgs, station_avr,
    sent_at, field_observed, is_office_task, user_created, user_last_edit
)
SELECT
    key, task_key, type, photo_uuid, photo_lens, ogh_id, oati_id,
    earthwork_id, localwork_id, avr_mos_id, sps, kgs, station_avr,
    sent_at, TRUE, is_office_task,
    ARRAY[{user_sql}, to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00'],
    ARRAY[{user_sql}, to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00']
FROM crm.tasks_field
WHERE lower(key::text) = lower({sql_str(field_key)})
ON CONFLICT (key) DO UPDATE SET field_observed = TRUE
""".strip(),
        f"DELETE FROM crm.tasks_field WHERE lower(key::text) = lower({sql_str(field_key)})",
        f"""
UPDATE crm.tasks
SET field_observed = TRUE
WHERE lower(key::text) = lower({sql_str(tasks_key)})
""".strip(),
        field_disruption_absent_sql(tasks_key, username, created_at),
    ]


def complete_observed_sql(field_key: str, tasks_key: str) -> list[str]:
    return [
        f"DELETE FROM crm.tasks_field WHERE lower(key::text) = lower({sql_str(field_key)})",
        f"""
UPDATE crm.tasks
SET field_observed = TRUE
WHERE lower(key::text) = lower({sql_str(tasks_key)})
""".strip(),
    ]


def track_insert_sql(archive: FieldZipArchive, username: str) -> str:
    track = archive.track
    assert track is not None
    started = ms_to_datetime(track.started_at_ms)
    task = track.task_key or archive.raw_task_key
    return f"""
INSERT INTO mggt_field.tracks (task, geom, started_at, duration_sec, name, comment, area_key, username)
VALUES (
    {sql_str(task)},
    {sql_geom_line(track.points)},
    {sql_ts(started)},
    {int(track.duration_sec)},
    {sql_str("trek")},
    {sql_str(format_duration(track.duration_sec))},
    {sql_str(archive.order_uuid)},
    {sql_str(username)}
)
""".strip()


def area_done_sql(area_key: str, exported_at: datetime | None) -> str:
    stamp = exported_at or datetime.now(timezone.utc)
    survey_date = stamp.astimezone(MOSCOW).date().isoformat()
    return f"""
UPDATE crm.tasks_area
SET status = 'done',
    date_survey = DATE '{survey_date}'
WHERE lower(key::text) = lower({sql_str(area_key)})
  AND lower(coalesce(status::text, '')) = 'wip_field'
""".strip()


def fetch_field_state(
    client: RestoreClient,
    order_uuid: str,
    submission_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    draw_ids = [item for item in (submission_ids or []) if item]
    if draw_ids:
        draw_sql = ", ".join(sql_str(item) for item in draw_ids)
        draw_clause = f" OR r.task IN ({draw_sql})"
        links_sql = f"""
  'report_links', COALESCE((
    SELECT json_agg(json_build_object('task', r.task, 'tasks_key', r.tasks_key::text))
    FROM mggt_field.reports r
    WHERE r.task IN ({draw_sql})
  ), '[]'::json)"""
    else:
        draw_clause = ""
        links_sql = "  'report_links', '[]'::json"
    sql = f"""
SELECT json_build_object(
  'field', (
    SELECT json_build_object(
      'key', tf.key::text,
      'task_key', tf.task_key::text,
      'executor', tf.executor,
      'rayon', tf.rayon,
      'type', tf.type
    )
    FROM crm.tasks_field tf
    WHERE tf.key = {sql_str(order_uuid)}::uuid
       OR tf.task_key = {sql_str(order_uuid)}::uuid
    ORDER BY tf.sent_at DESC NULLS LAST
    LIMIT 1
  ),
  'task', (
    SELECT json_build_object(
      'key', t.key::text,
      'field_observed', t.field_observed,
      'is_field_data', t.is_field_data,
      'type', t.type
    )
    FROM crm.tasks t
    WHERE t.key = COALESCE(
      (SELECT tf.task_key FROM crm.tasks_field tf
       WHERE tf.key = {sql_str(order_uuid)}::uuid
          OR tf.task_key = {sql_str(order_uuid)}::uuid
       LIMIT 1),
      {sql_str(order_uuid)}::uuid
    )
    LIMIT 1
  ),
  'in_clear', EXISTS(
    SELECT 1 FROM crm.tasks_clear c
    WHERE c.key = {sql_str(order_uuid)}::uuid
       OR c.task_key = {sql_str(order_uuid)}::uuid
  ),
  'report_tasks', COALESCE((
    SELECT json_agg(r.task)
    FROM mggt_field.reports r
    WHERE r.tasks_key IN (
      {sql_str(order_uuid)}::uuid,
      COALESCE((SELECT tf.task_key FROM crm.tasks_field tf
                WHERE tf.key = {sql_str(order_uuid)}::uuid LIMIT 1), {sql_str(order_uuid)}::uuid)
    )
       OR r.task = {sql_str(order_uuid)}
       {draw_clause}
  ), '[]'::json),
{links_sql}
)
""".strip()
    return client.psql_json(sql) or {}


def fetch_area_state(client: RestoreClient, area_uuid: str, track_task: str) -> dict[str, Any]:
    sql = f"""
SELECT json_build_object(
  'area', (
    SELECT json_build_object(
      'key', ta.key::text,
      'status', ta.status,
      'executor', ta.executor,
      'task_number', ta.task_number,
      'rayon', ta.rayon,
      'date_survey', ta.date_survey
    )
    FROM crm.tasks_area ta
    WHERE ta.key = {sql_str(area_uuid)}::uuid
    LIMIT 1
  ),
  'track_exists', EXISTS(
    SELECT 1 FROM mggt_field.tracks tr
    WHERE tr.task = {sql_str(track_task)}
       OR tr.area_key = {sql_str(area_uuid)}
       OR tr.task ILIKE {sql_str("%" + area_uuid + "%")}
  )
)
""".strip()
    return client.psql_json(sql) or {}


def report_exists(state: dict[str, Any], submission_id: str) -> bool:
    tasks = state.get("report_tasks") or []
    return submission_id in tasks


def _linked_task_key(archive: FieldZipArchive) -> str | None:
    for item in archive.features:
        key = (item.linked_task_key or "").strip()
        if key:
            return key
    return None


def _tasks_key_from_report_links(state: dict[str, Any], submissions: Sequence[DrawSubmission]) -> str | None:
    links = state.get("report_links") or []
    by_draw = {
        str(item.get("task")): item.get("tasks_key")
        for item in links
        if isinstance(item, dict)
    }
    for submission in submissions:
        key = by_draw.get(submission.id)
        if key:
            return str(key)
    return None


def _append_report_writes(
    plan: RestorePlan,
    archive: FieldZipArchive,
    username: str,
    tasks_key: str,
    state: dict[str, Any],
) -> bool:
    company = company_from_features(archive.features)
    any_write = False
    for submission in archive.submissions:
        photos = planned_photos_for_submission(archive, submission)
        if report_exists(state, submission.id):
            plan.actions.append(f"skip report {submission.id} (already in mggt_field.reports)")
            continue
        plan.photos.extend(photos)
        for photo in photos:
            plan.sql_statements.append(photo_insert_sql(photo, username))
        primary = primary_photo(submission.photos)
        primary_uuid = None
        if primary is not None:
            primary_uuid = next((p.uuid for p in photos if p.zip_path == primary.zip_path), None)
        created_at = ms_to_datetime(submission.created_at_ms) or archive.exported_at
        plan.sql_statements.append(
            report_insert_sql(
                submission=submission,
                tasks_key=tasks_key,
                username=username,
                company=company,
                photo_uuid=primary_uuid,
                created_at=created_at,
                banner=any(p.banner for p in photos),
            )
        )
        plan.actions.append(
            f"insert report {submission.id} event={submission.event_type} photos={len(photos)}"
        )
        any_write = True
    return any_write


def build_field_plan(
    archive: FieldZipArchive,
    username: str,
    state: dict[str, Any],
) -> RestorePlan:
    plan = RestorePlan(archive=archive, actions=[], photos=[], sql_statements=[])
    field_row = state.get("field") or {}
    task_row = state.get("task") or {}
    field_key = field_row.get("key")
    tasks_key = field_row.get("task_key") or task_row.get("key")
    plan.field_key = field_key
    plan.tasks_key = tasks_key

    if not archive.submissions:
        plan.skip_reason = "field ZIP has no draw submissions"
        return plan

    all_reports_present = all(report_exists(state, item.id) for item in archive.submissions)

    if not field_key:
        if all_reports_present and state.get("in_clear"):
            plan.skip_reason = "already restored (no tasks_field, reports present)"
            return plan

        leftover_key = _linked_task_key(archive) or _tasks_key_from_report_links(state, archive.submissions)
        if leftover_key and leftover_key.lower() != archive.order_uuid.lower():
            plan.tasks_key = leftover_key
            wrote = _append_report_writes(plan, archive, username, leftover_key, state)
            if wrote:
                plan.sql_statements.append(
                    f"""
UPDATE crm.tasks
SET field_observed = TRUE
WHERE lower(key::text) = lower({sql_str(leftover_key)})
""".strip()
                )
                plan.actions.append(f"update field_observed on assigned task {leftover_key}")
            elif all_reports_present:
                plan.skip_reason = "already restored (assigned order, no tasks_field)"
            else:
                plan.skip_reason = "nothing to write"
            return plan

        field_tasks_key = task_row.get("key") or archive.order_uuid
        plan.tasks_key = field_tasks_key
        plan.is_field_data_close = True
        if all_reports_present:
            plan.skip_reason = "already restored (field data)"
            return plan

        plan.sql_statements.append(insert_field_data_task_sql(field_tasks_key, username))
        plan.actions.append(f"insert crm.tasks {field_tasks_key} is_field_data")
        _append_report_writes(plan, archive, username, field_tasks_key, state)
        created_at = ms_to_datetime(archive.submissions[0].created_at_ms) or archive.exported_at
        plan.sql_statements.append(field_disruption_found_sql(field_tasks_key, username, created_at))
        plan.actions.append(f"emit field_disruption_found {field_tasks_key}")
        return plan

    if not tasks_key:
        plan.skip_reason = "crm.tasks.task_key not found"
        return plan

    any_write = _append_report_writes(plan, archive, username, tasks_key, state)

    if archive.as_clear:
        created_at = ms_to_datetime(archive.submissions[0].created_at_ms) or archive.exported_at
        plan.sql_statements.extend(
            complete_as_clear_sql(field_key, tasks_key, username, created_at)
        )
        plan.actions.append(f"complete as CLEAR {field_key} → tasks_clear + field_observed")
    else:
        plan.sql_statements.extend(complete_observed_sql(field_key, tasks_key))
        plan.actions.append(f"complete as OBSERVED {field_key} DELETE tasks_field + field_observed")
    any_write = True
    if not any_write and not plan.sql_statements:
        plan.skip_reason = "nothing to write"
    return plan


def build_area_plan(
    archive: FieldZipArchive,
    username: str,
    state: dict[str, Any],
) -> RestorePlan:
    plan = RestorePlan(archive=archive, actions=[], photos=[], sql_statements=[])
    area = state.get("area") or {}
    status = area.get("status")
    plan.area_status = status
    track_task = (archive.track.task_key if archive.track else None) or archive.raw_task_key

    skip_close, reason = should_skip_area_close(archive, status)
    if skip_close and is_junk_track(archive):
        plan.skip_reason = reason
        plan.actions.append(f"SKIP area {archive.order_uuid}: {reason}")
        return plan

    if not state.get("track_exists") and archive.track is not None and not is_junk_track(archive):
        plan.sql_statements.append(track_insert_sql(archive, username))
        plan.actions.append(
            f"insert track {track_task} points={len(archive.track.points)} "
            f"duration={archive.track.duration_sec}s"
        )
    elif state.get("track_exists"):
        plan.actions.append("skip track (already present)")

    if skip_close:
        plan.actions.append(f"skip area close: {reason}")
        if not plan.sql_statements:
            plan.skip_reason = reason
        return plan

    plan.sql_statements.append(area_done_sql(archive.order_uuid, archive.exported_at))
    plan.actions.append(f"mark tasks_area {archive.order_uuid} wip_field → done")
    return plan


def build_plan(archive: FieldZipArchive, username: str, client: RestoreClient | None) -> RestorePlan:
    if archive.kind == "area":
        state: dict[str, Any] = {}
        if client is not None:
            track_task = (archive.track.task_key if archive.track else None) or archive.raw_task_key
            state = fetch_area_state(client, archive.order_uuid, track_task)
        else:
            state = {"area": {"status": "wip_field"}, "track_exists": False}
        return build_area_plan(archive, username, state)
    state = {}
    if client is not None:
        state = fetch_field_state(
            client,
            archive.order_uuid,
            [item.id for item in archive.submissions],
        )
    else:
        state = {
            "field": {"key": archive.order_uuid, "task_key": archive.order_uuid},
            "task": {"key": archive.order_uuid, "field_observed": False, "is_field_data": False},
            "in_clear": False,
            "report_tasks": [],
            "report_links": [],
        }
    return build_field_plan(archive, username, state)


def extract_zip_bytes(archive: FieldZipArchive, zip_path: str) -> bytes:
    with zipfile.ZipFile(archive.path) as zf:
        try:
            return zf.read(zip_path)
        except KeyError:
            target = zip_path.replace("\\", "/")
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name == target or name.endswith("/" + Path(target).name):
                    return zf.read(info)
    raise FileNotFoundError(f"{archive.path.name}: missing {zip_path}")


def warn_missing_photos(plan: RestorePlan) -> None:
    for photo in plan.photos:
        try:
            extract_zip_bytes(plan.archive, photo.zip_path)
        except FileNotFoundError:
            plan.warnings.append(f"в ZIP нет фото {photo.zip_path}")


def apply_plan(plan: RestorePlan, client: RestoreClient, photo_dir: str) -> None:
    payloads: list[tuple[str, bytes, int]] = []
    for photo in plan.photos:
        raw = extract_zip_bytes(plan.archive, photo.zip_path)
        mtime = int(photo.taken_at.timestamp()) if photo.taken_at else int(datetime.now(timezone.utc).timestamp())
        payloads.append((photo.file_name, raw, mtime))
    client.copy_photos(payloads, photo_dir)
    client.apply_sql(plan.sql_statements)


def snapshot_keys(client: RestoreClient, uuids: Sequence[str]) -> str:
    arr = ",".join(sql_str(item) + "::uuid" for item in uuids)
    text_arr = ",".join(sql_str(item) for item in uuids)
    sql = f"""
WITH keys AS (
  SELECT unnest(ARRAY[{arr}]) AS k
),
task_keys AS (
  SELECT tf.task_key AS k FROM crm.tasks_field tf WHERE tf.key IN (SELECT k FROM keys)
  UNION
  SELECT tc.task_key FROM crm.tasks_clear tc WHERE tc.key IN (SELECT k FROM keys)
  UNION
  SELECT k FROM keys
)
SELECT json_build_object(
  'tasks_field', (
    SELECT COALESCE(json_agg(json_build_object('key', tf.key, 'task_key', tf.task_key) ORDER BY tf.key), '[]'::json)
    FROM crm.tasks_field tf WHERE tf.key IN (SELECT k FROM keys)
  ),
  'tasks_clear', (
    SELECT COALESCE(json_agg(json_build_object('key', tc.key, 'task_key', tc.task_key, 'field_observed', tc.field_observed) ORDER BY tc.key), '[]'::json)
    FROM crm.tasks_clear tc WHERE tc.key IN (SELECT k FROM keys)
  ),
  'tracks', (
    SELECT COUNT(*) FROM mggt_field.tracks tr
    WHERE tr.area_key IN ({text_arr})
       OR tr.task ILIKE ANY (ARRAY[{",".join(sql_str("%" + item + "%") for item in uuids)}])
  ),
  'stats', (
    SELECT COALESCE(json_agg(json_build_object(
      'action', s.action, 'object_key', s.object_key, 'user_login', s.user_login, 'created_at', s.created_at
    ) ORDER BY s.created_at), '[]'::json)
    FROM crm.statistics s
    WHERE s.object_key IN (SELECT k FROM task_keys)
  )
)
""".strip()
    return json.dumps(client.psql_json(sql), ensure_ascii=False, indent=2, default=str)
