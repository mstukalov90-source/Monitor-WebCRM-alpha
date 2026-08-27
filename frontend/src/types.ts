export type UserRole = 'admin' | 'field' | 'office' | 'manager'

export interface AuthUser {
  login: string
  name?: string
  role: UserRole
  work_zones: number[]
  allowed_task_sources: TaskSource[]
  default_task_source: TaskSource
  can_collect: boolean
  can_manage_personnel: boolean
  can_generate_letters: boolean
  can_manage_field_task_status: boolean
  can_postpone_tasks: boolean
  can_create_users: boolean
  can_view_server_monitor: boolean
  /** Present on login for API/QGIS clients; browser uses cookie and may ignore. */
  token?: string
}

export interface PersonnelUserCreate {
  login: string
  name: string
  password: string
  role: UserRole
  work_zones: number[]
}

export interface PersonnelUser {
  uuid: string
  login: string
  name?: string
  role: UserRole
  work_zones: number[]
  district_names: string[]
}

export type ZipCloseOutcome = 'ok' | 'skip' | 'mismatch' | 'error'
export type ZipCloseKind = 'field_order' | 'area' | 'unknown'
export type ZipCloseAction = 'clear' | 'observed' | 'area_done' | 'track_only'

export interface ZipCloseItem {
  filename: string
  kind: ZipCloseKind
  order_number: string | null
  order_uuid: string | null
  rayon: string | null
  outcome: ZipCloseOutcome
  will_write: boolean
  close_kind: ZipCloseAction | null
  photo_count: number
  db_status: string | null
  actions: string[]
  warnings: string[]
  skip_reason: string | null
  error: string | null
  applied?: boolean
  apply_error?: string | null
}

export interface ZipClosePreview {
  preview_id: string
  username: string
  can_apply: boolean
  items: ZipCloseItem[]
}

export interface ZipCloseApplyResult {
  username: string
  applied_count: number
  items: ZipCloseItem[]
}

export interface DistrictOption {
  gid: number
  rayon: string
}

export interface AssignableTask {
  key: string
  table: 'active' | 'field' | 'clear' | 'area'
  executor: string | null
  type?: string | null
  task_key?: string | null
  sent_at?: string | null
  rayon?: string | null
  status?: string | null
  area?: number | null
  date_survey?: string | null
  task_number?: string | null
}

export type WorkflowTargetStatus = 'active' | 'field' | 'clear'

export interface BulkStatusResult {
  updated: number
  skipped: number
  not_found: number
  failed: { task_key: string; error: string }[]
}

export interface FieldStatisticsSummary {
  user_login: string
  user_role: string
  camera_surveys: number
  disruption_absent: number
  disruption_found: number
  orders_closed: number
  orders_closed_ha: number
  period_from: string | null
  period_to: string | null
}

export interface OfficeStatisticsBreakdown {
  user_login: string
  user_role: string
  object_type: string
  action: string
  action_count: number
  area_hectares: number
  period_from: string | null
  period_to: string | null
}

export interface StatisticsActionDetail {
  user_login: string
  user_role: string
  object_type: string
  action: string
  object_key: string
  created_at: string
  task_number: string | null
  rayon: string | null
  area_hectares: number
  duration_minutes: number | null
  order_score?: FieldScoreValue | null
}

export interface PersonnelStatistics {
  field_summary: FieldStatisticsSummary[]
  office_breakdown: OfficeStatisticsBreakdown[]
  action_details: StatisticsActionDetail[]
  date_from: string
  date_to: string
  scope: 'all' | 'self'
}

export interface GeoStatisticsRow {
  okrug: string | null
  rayon: string | null
  orders_closed: number
  orders_closed_ha: number
  orders_open: number
  orders_open_ha: number
  pre_analise_completed: number
  analise_completed: number
  progress_pct: number | null
}

export interface GeoStatistics {
  okrugs: GeoStatisticsRow[]
  rayons: GeoStatisticsRow[]
  date_from: string
  date_to: string
}

export interface OrderClosuresStatistics {
  closures: StatisticsActionDetail[]
  date_from: string
  date_to: string
}

export type ReportValueType = 'str' | 'int' | 'float' | 'datetime' | 'bool'
export type ReportNestMode = 'related_sheet' | 'nested_rows'

export interface ReportColumnDef {
  id: string
  label: string
  value_type: ReportValueType
  format?: string | null
}

export interface ReportFilterOption {
  value: string
  label: string
}

export interface ReportFilterDef {
  id: string
  label: string
  type: 'multi'
  options: ReportFilterOption[]
}

export interface ReportChildDataset {
  id: string
  label: string
}

export interface ReportDatasetDef {
  id: string
  label: string
  description: string
  columns: ReportColumnDef[]
  filters: ReportFilterDef[]
  parent_datasets: string[]
  child_datasets: ReportChildDataset[]
}

export interface ReportSheetSpec {
  id: string
  dataset: string
  title: string
  columns: string[]
  filters: Record<string, string[]>
  parent_sheet?: string | null
  nest?: ReportNestMode
}

export interface ReportSpec {
  name: string
  sheets: ReportSheetSpec[]
}

export interface ReportPreset {
  id: string
  name: string
  spec: ReportSpec
}

export interface ReportNestModeOption {
  id: ReportNestMode
  label: string
}

export interface ReportCatalog {
  datasets: ReportDatasetDef[]
  presets: ReportPreset[]
  nest_modes: ReportNestModeOption[]
  max_export_rows: number
}

export interface ReportTemplate {
  id: string
  name: string
  spec: ReportSpec
  created_at: string
  updated_at: string
}

export interface OrderStatusFeed {
  events: StatisticsActionDetail[]
  counts?: Record<string, number>
  date_from: string
  date_to: string
}

export interface AnaliseDispatchOfficeUser {
  login: string
  name: string
}

export interface AnaliseDispatchContext {
  order_key: string
  task_number: string | null
  rayon: string | null
  workflow: AnaliseWorkflowStatus
  lock_holder: string | null
  has_analise_tasks: boolean
  task_count: number
  office_users: AnaliseDispatchOfficeUser[]
}

export interface AnaliseDispatchResult {
  status: string
  mode: 'start' | 'complete'
  assignee_login: string
}

export interface TaskViewContext {
  task_key: string
  group_name: string
  subgroup_name: string
  feature: TaskFeature
}

export interface TaskGroupMapFeature {
  task_key: string
  subgroup_name: string
  source: string
  layer_name: string
  layer_key: string
  geometry?: GeoJSON.Geometry | null
  attributes: Record<string, unknown>
}

export interface TaskGroupMap {
  rayon: string
  group_name: string
  selected_task_key: string
  features: TaskGroupMapFeature[]
  errors: string[]
}

export type NearbyContextKind = 'orders' | 'kgs' | 'sps' | 'ops'

export const NEARBY_CONTEXT_BUTTONS: { kind: NearbyContextKind; label: string }[] = [
  { kind: 'sps', label: 'Посмотреть СПС' },
  { kind: 'ops', label: 'Посмотреть ОПС' },
  { kind: 'kgs', label: 'Посмотреть КГС' },
  { kind: 'orders', label: 'Посмотреть все ордера' },
]

export interface NearbyFeatureStyle {
  color?: string
  weight?: number
  fillColor?: string
  fillOpacity?: number
  opacity?: number
  dashArray?: string
  radius?: number
}

export interface NearbyContextFeature {
  id: string
  table: string
  geometry: GeoJSON.Geometry
  properties: Record<string, unknown>
  style: NearbyFeatureStyle
  label?: string | null
}

export interface NearbyContextResult {
  kind: NearbyContextKind
  radius_m: number
  features: NearbyContextFeature[]
  errors: string[]
  count: number
}

export interface OrderSearchHit {
  subgroup_name: string
  layer_name: string
  layer_key: string
  task_key?: string | null
  attributes: Record<string, unknown>
  geometry?: GeoJSON.Geometry | null
  in_selected_rayon: boolean
}

export interface OrderSearchResult {
  query: string
  rayon: string
  hits: OrderSearchHit[]
  errors: string[]
}

export type AppView =
  | 'workspace'
  | 'personnel'
  | 'statistics'
  | 'order_tracks'
  | 'employee_locations'
  | 'field_score'
  | 'server_monitor'
  | 'ozn_match'

export type FieldScoreValue = 'unsatisfactory' | 'satisfactory' | 'good'

export const FIELD_SCORE_LABELS: Record<FieldScoreValue, string> = {
  unsatisfactory: 'Неудовлетворительно',
  satisfactory: 'Удовлетворительно',
  good: 'Хорошо',
}

export interface FieldScoreOrder {
  order_key: string
  task_number: string | null
  rayon: string | null
  area: number | null
  status: string | null
  date_survey: string | null
  geometry?: GeoJSON.Geometry | null
}

export interface FieldScoreTask {
  task_key: string
  report_id?: number | null
  source: string
  group_name: string
  subgroup_name: string
  label: string
  attributes: Record<string, unknown>
  geometry?: GeoJSON.Geometry | null
  sent_at: string | null
}

export interface FieldScoreTrack {
  id: string
  attributes: Record<string, unknown>
  geometry: GeoJSON.Geometry
  buffer_geometry?: GeoJSON.Geometry | null
}

export interface FieldScoreSaved {
  order_key: string
  task_scores: Record<string, FieldScoreValue>
  track_coverage_pct: number | null
  order_score: FieldScoreValue | null
  scored_by: string
  scored_at: string | null
  updated_at: string | null
  coverage_hint?: FieldScoreValue | null
}

export interface FieldScoreContext {
  order: FieldScoreOrder
  tasks: FieldScoreTask[]
  tracks: FieldScoreTrack[]
  track_coverage_pct: number | null
  coverage_hint: FieldScoreValue | null
  buffer_meters: number
  saved: FieldScoreSaved | null
  errors: string[]
}

export interface TrackFeature {
  id: string
  attributes: Record<string, unknown>
  geometry: GeoJSON.Geometry
}

export interface OrderTracksResult {
  district_name: string
  tracks: TrackFeature[]
  errors: string[]
}

export interface OznMatchOrder {
  order_key: string
  task_number: string | null
  rayon: string | null
  area: number | null
  status: string | null
  executor: string | null
  match_count: number
  geometry: GeoJSON.Geometry
}

export interface OznMatchObject {
  id: string
  label: string
  order_name?: string | null
  ozn_date?: string | null
  executor?: string | null
  geometry: GeoJSON.Geometry
}

export interface OznMatchResult {
  district_name: string
  orders: OznMatchOrder[]
  ozn_objects: OznMatchObject[]
  matches: Record<string, string[]>
  errors: string[]
}

export interface TrackTableColumn {
  field: string
  label: string
  format?: 'date' | 'datetime' | 'duration_sec'
}

export const TRACK_TABLE_COLUMNS: TrackTableColumn[] = [
  { field: 'username', label: 'Исполнитель' },
  { field: 'started_at', label: 'Начало', format: 'datetime' },
  { field: 'duration_sec', label: 'Продолжительность', format: 'duration_sec' },
]

export function formatTrackTableCell(value: unknown, format?: TrackTableColumn['format']): string {
  if (value == null || value === '') return ''
  if (format === 'datetime') {
    const d = new Date(String(value))
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('ru-RU')
  }
  if (format === 'date') {
    const d = new Date(String(value))
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString('ru-RU')
  }
  if (format === 'duration_sec') {
    const sec = Number(value)
    if (Number.isNaN(sec)) return String(value)
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${String(s).padStart(2, '0')}`
  }
  return String(value)
}

export interface EmployeeLocationFeature {
  id: string
  attributes: Record<string, unknown>
  geometry: GeoJSON.Geometry
}

export interface EmployeeLocationsResult {
  district_name: string
  locations: EmployeeLocationFeature[]
  errors: string[]
}

export interface EmployeeLocationTableColumn {
  field: string
  label: string
  format?: 'datetime_short'
}

export const EMPLOYEE_LOCATION_TABLE_COLUMNS: EmployeeLocationTableColumn[] = [
  { field: 'user', label: 'Сотрудник' },
  { field: 'time', label: 'Обновлено', format: 'datetime_short' },
  { field: 'number', label: 'Заказ' },
]

export function formatEmployeeLocationTableCell(
  value: unknown,
  format?: EmployeeLocationTableColumn['format'],
): string {
  if (value == null || value === '') return ''
  if (format === 'datetime_short') {
    const d = new Date(String(value))
    if (Number.isNaN(d.getTime())) return String(value)
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  return String(value)
}

export const HOOD_BOUNDARIES_DISPLAY_NAME = 'Границы районов'
export const DISTRICT_RAYON_FIELD = 'rayon'
export const DISTRICT_OKRUG_FIELD = 'okrug_shor'
export const EXCLUDED_OKRUG_SHORT = ['НАО', 'ТАО'] as const
/** Bbox Москвы и ближайшей области: minLon,minLat,maxLon,maxLat */
export const MOSCOW_MAP_BBOX = '36.8,55.4,38.2,56.1'

/** Collapse whitespace (incl. CR/LF) and strip spaces around hyphens. */
export function normalizeRayonName(value: string): string {
  return value.replace(/\s+/g, ' ').trim().replace(/\s*-\s*/g, '-')
}

export function resolveRayonFromDistricts(raw: unknown, districts: string[]): string {
  const normalized = normalizeRayonName(String(raw ?? ''))
  if (!normalized) return ''
  const match = districts.find((d) => normalizeRayonName(d) === normalized)
  return match ?? normalized
}

export function isExcludedDistrictOkrug(okrugShor: unknown): boolean {
  const value = normalizeRayonName(String(okrugShor ?? ''))
  return (EXCLUDED_OKRUG_SHORT as readonly string[]).includes(value)
}

export function filterDistrictGeoJson(
  geojson: GeoJSON.FeatureCollection,
): GeoJSON.FeatureCollection {
  return {
    ...geojson,
    features: geojson.features.filter(
      (feature) => !isExcludedDistrictOkrug(feature.properties?.[DISTRICT_OKRUG_FIELD]),
    ),
  }
}

export interface Symbology {
  color?: string
  fill_color?: string
  outline_color?: string
  fill_opacity?: number
  outline_width?: number
  width?: number
  size?: number
  opacity?: number
  marker_type?: string
  center_color?: string
  outer_color?: string
  outer_width?: number
}

export interface LayerConfig {
  layer_key: string
  display_name: string
  geometry_type: string
  symbology: Symbology
  placeholder?: boolean
}

export interface LayerGroupConfig {
  name: string
  default_visibility: boolean
  layers: LayerConfig[]
  groups: LayerGroupConfig[]
}

export type TaskSource =
  | 'active'
  | 'field'
  | 'delay'
  | 'done_legal'
  | 'done_illegal'
  | 'clear'
  | 'area'

export type TaskFilterSelection = '' | TaskSource

export const TASK_FILTER_NONE = '' as const
export const TASK_FILTER_LABEL = 'Задачи'

export type AreaStatus = 'free' | 'wip' | 'wip_field' | 'in_pause' | 'done'

export const AREA_STATUS_COLORS: Record<AreaStatus, string> = {
  free: '#ff9800',
  wip: '#fdd835',
  wip_field: '#fdd835',
  in_pause: '#e53935',
  done: '#43a047',
}

export const TASK_SECTION_TASK_SOURCES: TaskSource[] = [
  'active',
  'field',
  'delay',
  'done_legal',
  'done_illegal',
  'clear',
]

export const TASK_SECTION_ORDER_SOURCES: TaskSource[] = ['area']

export interface LinkedTaskFeature {
  link_column: string
  layer_key: string
  layer_name: string
  geometry?: GeoJSON.Geometry | null
  attributes: Record<string, unknown>
  business_id?: string
  link_kind?: 'link' | 'sibling'
}

export interface FieldReportFeature {
  report_id: number
  report_task?: string | null
  geometry: GeoJSON.Geometry
  attributes: Record<string, unknown>
  comment?: string | null
  photo_key?: string | null
}

export interface OatiLetterPhoto {
  id: number
  file_path: string
  banner: boolean
  created_at?: string | null
  label?: string | null
  image_url: string
}

export interface OatiLetterDraft {
  task_key: string
  report_id: number
  rayon: string
  street: string
  today: string
  coordinates: string
  lon: number
  lat: number
  incident_datetime: string
  customer: string
  executor: string
  address: string
  engineering: string
  description: string
  violation: string
  sps: string
  kgs: string
  photos: OatiLetterPhoto[]
  map_warning?: string | null
  task_geometry_visibility: string
  address_auto: boolean
  address_has_house: boolean
  address_geocode: string
  address_mos: string
  engineering_options: string[]
  violation_options: string[]
  map_scales: number[]
  map_scale_default: number
}

export interface OatiLetterGeneratePayload {
  customer: string
  executor: string
  address: string
  engineering: string
  description: string
  violation?: string
  sps: string
  kgs: string
  violation_names: string[]
  photo_ids: number[]
  map_scale: number
}

export interface OatiLetterGenerateResult {
  fid: number
  filename: string
  download_url: string
}

export interface MissingLink {
  link_column: string
  business_id: string
}

export interface TaskHighlightPopup {
  groupName: string
  subgroupName: string
  feature: TaskFeature
  taskKey?: string
}

export interface TaskHighlight {
  primary?: GeoJSON.Geometry | null
  linked: LinkedTaskFeature[]
  fieldReports?: FieldReportFeature[]
  missingLinks?: MissingLink[]
  popup?: TaskHighlightPopup
  /** Task key for field-report photo clicks (set even when popup is omitted). */
  taskKey?: string
  notificationGroup?: {
    value: string
    total: number
  }
}

export interface TaskFeature {
  layer_name: string
  layer_key: string
  attributes: Record<string, unknown>
  geometry?: GeoJSON.Geometry | null
  task_key?: string | null
  sent_at?: string | null
}

export interface TaskSubgroup {
  name: string
  date_field?: string | null
  features: TaskFeature[]
}

export interface TaskGroup {
  name: string
  subgroups: TaskSubgroup[]
}

export interface TaskResult {
  district_name: string
  filter_date_from: string
  filter_date_to: string
  apply_date_filter: boolean
  groups: TaskGroup[]
  errors: string[]
  task_source?: TaskSource
  persist_stats?: {
    inserted: number
    skipped: number
    invalid: number
    pending?: boolean
  }
}

export interface CollectPlanLayer {
  group_name: string
  subgroup_name: string
  layer_key: string
  layer_name: string
}

export interface CollectPlan {
  district_name: string
  filter_date_from: string
  filter_date_to: string
  apply_date_filter: boolean
  groups: TaskGroup[]
  layers: CollectPlanLayer[]
  errors: string[]
}

export interface CollectLayerChunk {
  group_name: string
  subgroup_name: string
  layer_key: string
  features: TaskFeature[]
  errors: string[]
}

export interface CollectProgress {
  current: number
  total: number
  layerName: string
}

export interface AiPhotoMeta {
  uuid: string
  image_name: string
  date: string | null
  azimuth_deg: number | null
  order_id: string | null
  url: string
  bboxes?: unknown
}

export type CameraBlockMode =
  | 'until_field_observed'
  | 'until_quarter'
  | 'until_date'
  | 'until_order_end'

export interface CameraBlockOptions {
  cam_id: string | null
  order_end_date: string | null
}

export interface DitPhotoMeta {
  result_id: string
  image: string
  image_name: string
  url: string
  bboxes?: unknown
}

export type PhotoViewSource = 'genplan' | 'dit'

export interface FieldPhoto {
  id: number
  file_path: string
  banner: boolean
  created_at: string | null
  label: string | null
  image_url: string
}

export interface FieldPhotosResult {
  photos: FieldPhoto[]
  banner_missing: boolean
  comment?: string | null
}

export interface LensPhoto {
  id: number
  file_path: string
  relative_path: string
  windows_path: string
  file_name: string
}

export interface LensPhotosResult {
  external_report_id: string
  photos: LensPhoto[]
}

export const AI_PHOTO_SUBGROUP = 'Фото после обработки ИИ (ГенПлан)'
export const AI_PHOTO_LAYER_KEY = 'фотографии_после_обработки_ии'
export const DIT_PHOTO_SUBGROUP = 'Фото после обработки ИИ (ДИТ)'
export const DIT_PHOTO_LAYER_KEY = 'фотографии_после_обработки_ии_дит'
export const LENS_PHOTO_SUBGROUP = 'Фото разрытий и строек'
export const LENS_PHOTO_LAYER_KEY = 'фото_разрытий_и_строек'
export const OGH_DISRUPTION_SUBGROUP = 'Разрытия из полигонов ОГХ'
export const FIELD_DATA_SUBGROUP = 'Полевые данные'
export const FIELD_DATA_LAYER_KEY = 'field_data'
export const OFFICE_ANALYSIS_SUBGROUP = 'Задачи из камерального анализа'
export const OFFICE_DATA_LAYER_KEY = 'office_data'
export const OATI_ORDERS_SUBGROUP = 'Ордера ОАТИ'
export const EARTHWORK_SUBGROUP = 'Уведомления на земляные работы'
export const AVR_SUBGROUP = 'Аварийно-восстановительные работы'
export const LOCAL_REPAIR_SUBGROUP = 'Текущие локальные ремонты'
export const CRM_GROUP_ORDERS = 'Новые ордера ОАТИ, АВР и земляные работы'

export interface TaskTableColumn {
  field: string
  label: string
  format?: 'date' | 'field_observed' | 'area_status' | 'area_hectares' | 'user_login'
}

export const FIELD_OBSERVED_COLUMN: TaskTableColumn = {
  field: 'field_observed',
  label: 'Обследовано в поле',
  format: 'field_observed',
}

export const TASK_TABLE_COLUMNS: Partial<Record<string, TaskTableColumn[]>> = {
  [AI_PHOTO_SUBGROUP]: [
    { field: 'azimuth_deg', label: 'Угол камеры' },
    { field: 'date', label: 'Дата съёмки', format: 'date' },
  ],
  [DIT_PHOTO_SUBGROUP]: [
    { field: 'created_at', label: 'Дата съёмки', format: 'date' },
  ],
  [LENS_PHOTO_SUBGROUP]: [
    { field: 'comment', label: 'Комментарий' },
    { field: 'created_at', label: 'Дата съёмки', format: 'date' },
  ],
  [OGH_DISRUPTION_SUBGROUP]: [
    { field: 'loaded_at', label: 'Дата загрузки', format: 'date' },
  ],
  [OATI_ORDERS_SUBGROUP]: [
    { field: 'order_number', label: 'Номер ордера' },
    { field: 'work_start_date', label: 'Дата начала работ', format: 'date' },
    { field: 'work_end_date', label: 'Дата окончания работ', format: 'date' },
    { field: 'general_contractor', label: 'Исполнитель' },
    { field: 'customer_construction', label: 'Заказчик' },
  ],
  [EARTHWORK_SUBGROUP]: [
    { field: 'executor', label: 'Исполнитель', format: 'user_login' },
    { field: 'registration_number_notifications', label: 'Номер уведомления' },
    { field: 'work_start_date', label: 'Дата начала работ', format: 'date' },
    { field: 'work_end_date', label: 'Дата окончания работ', format: 'date' },
  ],
  [AVR_SUBGROUP]: [
    { field: 'balanceholder', label: 'Заказчик' },
    { field: 'lead_of_work', label: 'Исполнитель' },
    { field: 'em_call_reg_num', label: 'Номер аварийного вызова' },
    { field: 'work_start_date', label: 'Дата начала работ', format: 'date' },
    { field: 'work_end_date', label: 'Дата окончания работ', format: 'date' },
    { field: 'engineering_net_obj', label: 'Тип коммуникаций' },
  ],
  [LOCAL_REPAIR_SUBGROUP]: [
    { field: 'customer', label: 'Заказчик' },
    { field: 'global_id', label: 'Номер data.mos' },
    { field: 'actual_start_date', label: 'Дата начала работ', format: 'date' },
    { field: 'actual_end_date', label: 'Дата окончания работ', format: 'date' },
  ],
  [FIELD_DATA_SUBGROUP]: [
    { field: 'created_at', label: 'Дата обследования', format: 'date' },
  ],
  [OFFICE_ANALYSIS_SUBGROUP]: [
    { field: 'created_at', label: 'Дата создания', format: 'date' },
    { field: 'oati_id', label: 'ОАТИ' },
    { field: 'earthwork_id', label: 'Земляные работы' },
    { field: 'avr_mos_id', label: 'АВР' },
  ],
}

const EARTHWORK_OBJECTIVE_COLUMNS: TaskTableColumn[] = [
  { field: 'earthwork_objectives', label: 'Назначение работ' },
  {
    field: 'objectives_of_the_installation_of_temporary_fences',
    label: 'Назначение установки временных ограждений',
  },
  {
    field: 'objectives_of_the_placement_of_temporary_objects',
    label: 'Назначение размещения временных ограждений',
  },
]

/** Extra source fields shown only in the execute-task modal, not in the table or popup. */
export const TASK_MODAL_EXTRA_COLUMNS: Partial<Record<string, TaskTableColumn[]>> = {
  [OATI_ORDERS_SUBGROUP]: EARTHWORK_OBJECTIVE_COLUMNS,
  [EARTHWORK_SUBGROUP]: EARTHWORK_OBJECTIVE_COLUMNS,
  [AVR_SUBGROUP]: [{ field: 'damage_type', label: 'Тип повреждения' }],
}

export const ORDER_GROUP_SEARCH_FIELDS: Record<
  string,
  { id: string; executor?: string; customer?: string; address?: string }
> = {
  [OATI_ORDERS_SUBGROUP]: {
    id: 'order_number',
    executor: 'general_contractor',
    customer: 'customer_construction',
    address: 'work_place_description',
  },
  [EARTHWORK_SUBGROUP]: {
    id: 'registration_number_notifications',
    executor: 'executor',
    address: 'work_place_description',
  },
  [AVR_SUBGROUP]: {
    id: 'em_call_reg_num',
    executor: 'lead_of_work',
    customer: 'balanceholder',
    address: 'work_place_description',
  },
  [LOCAL_REPAIR_SUBGROUP]: {
    id: 'global_id',
    customer: 'customer',
    address: 'work_place_description',
  },
}

export const AREA_TASK_TABLE_COLUMNS: TaskTableColumn[] = [
  { field: 'executor_name', label: 'Исполнитель', format: 'user_login' },
  { field: 'status', label: 'Статус', format: 'area_status' },
  { field: 'task_number', label: 'Заказ' },
  { field: 'area', label: 'Площадь', format: 'area_hectares' },
  { field: 'date_survey', label: 'Дата обследования', format: 'date' },
  { field: 'analise', label: 'Анализ', format: 'field_observed' },
]

export const AREA_TASK_STATUS_LABELS: Record<AreaStatus, string> = {
  free: 'Свободный заказ',
  wip: 'На обследовании',
  wip_field: 'В работе в поле',
  in_pause: 'Приостановлен в поле',
  done: 'Завершённый',
}

export function formatAreaStatus(value: unknown): string {
  if (value == null || value === '') return ''
  const key = String(value).trim().toLowerCase()
  if (key in AREA_TASK_STATUS_LABELS) return AREA_TASK_STATUS_LABELS[key as AreaStatus]
  return String(value)
}

export function formatAreaHectares(value: unknown): string {
  if (value == null || value === '') return ''
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  const hectares = num / 10_000
  return `${hectares.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} га`
}

export function isAnaliseComplete(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === 'boolean') return value
  const text = String(value).trim().toLowerCase()
  return ['true', 't', '1', 'yes', 'да'].includes(text)
}

export function formatAnaliseStatus(value: unknown): 'Обработан' | 'Не обработан' {
  return isAnaliseComplete(value) ? 'Обработан' : 'Не обработан'
}

export type AnaliseWorkflowStatus = 'idle' | 'in_progress' | 'paused' | 'done'

function hasAnaliseTimestamp(value: unknown): boolean {
  return value != null && String(value).trim() !== ''
}

export function analiseWorkflowStatus(attrs: Record<string, unknown>): AnaliseWorkflowStatus {
  if (isAnaliseComplete(attrs.analise)) return 'done'
  if (hasAnaliseTimestamp(attrs.analise_paused_at)) return 'paused'
  if (hasAnaliseTimestamp(attrs.analise_started_at)) return 'in_progress'
  return 'idle'
}

export function canStartAnalise(attrs: Record<string, unknown>, currentLogin: string): boolean {
  const status = analiseWorkflowStatus(attrs)
  const login = currentLogin.trim()
  const startedBy = String(attrs.analise_started_by ?? '').trim()
  if (status === 'idle') return true
  if (status === 'paused') return startedBy === login
  if (status === 'in_progress') return startedBy === login
  return false
}

export function formatAnaliseWorkflowStatus(attrs: Record<string, unknown>): string {
  const status = analiseWorkflowStatus(attrs)
  if (status === 'done') return 'Обработан'
  if (status === 'idle') return 'Не обработан'
  if (status === 'paused') return 'Приостановлен'
  const by = String(attrs.analise_started_by ?? '').trim()
  return by ? `В работе (${by})` : 'В работе'
}

export function analiseWorkflowStatusClass(status: AnaliseWorkflowStatus): string {
  switch (status) {
    case 'done':
      return 'area-analise-status-done'
    case 'in_progress':
      return 'area-analise-status-progress'
    case 'paused':
      return 'area-analise-status-paused'
    default:
      return 'area-analise-status-pending'
  }
}

export type OfficeWorkMode = 'pre_analise' | 'analise' | 'map'
export type OfficeAnaliseStage = 'pre_analise' | 'analise'

export function preAnaliseWorkflowStatus(attrs: Record<string, unknown>): AnaliseWorkflowStatus {
  if (isAnaliseComplete(attrs.pre_analise)) return 'done'
  if (hasAnaliseTimestamp(attrs.pre_analise_paused_at)) return 'paused'
  if (hasAnaliseTimestamp(attrs.pre_analise_started_at)) return 'in_progress'
  return 'idle'
}

export function canStartPreAnalise(attrs: Record<string, unknown>, currentLogin: string): boolean {
  const status = preAnaliseWorkflowStatus(attrs)
  const login = currentLogin.trim()
  const startedBy = String(attrs.pre_analise_started_by ?? '').trim()
  if (status === 'idle') return true
  if (status === 'paused') return startedBy === login
  if (status === 'in_progress') return startedBy === login
  return false
}

export function formatPreAnaliseWorkflowStatus(attrs: Record<string, unknown>): string {
  const status = preAnaliseWorkflowStatus(attrs)
  if (status === 'done') return 'Подготовлен'
  if (status === 'idle') return 'Не подготовлен'
  if (status === 'paused') return 'Приостановлен'
  const by = String(attrs.pre_analise_started_by ?? '').trim()
  return by ? `В подготовке (${by})` : 'В подготовке'
}

export function stageWorkflowStatus(
  attrs: Record<string, unknown>,
  stage: OfficeAnaliseStage,
): AnaliseWorkflowStatus {
  return stage === 'pre_analise' ? preAnaliseWorkflowStatus(attrs) : analiseWorkflowStatus(attrs)
}

export function canStartStage(
  attrs: Record<string, unknown>,
  currentLogin: string,
  stage: OfficeAnaliseStage,
): boolean {
  return stage === 'pre_analise'
    ? canStartPreAnalise(attrs, currentLogin)
    : canStartAnalise(attrs, currentLogin)
}

export function formatStageWorkflowStatus(
  attrs: Record<string, unknown>,
  stage: OfficeAnaliseStage,
): string {
  return stage === 'pre_analise'
    ? formatPreAnaliseWorkflowStatus(attrs)
    : formatAnaliseWorkflowStatus(attrs)
}

function stageOwnerLogins(
  attrs: Record<string, unknown>,
  stage: OfficeAnaliseStage,
): { startedBy: string; pausedBy: string } {
  if (stage === 'pre_analise') {
    return {
      startedBy: String(attrs.pre_analise_started_by ?? '').trim(),
      pausedBy: String(attrs.pre_analise_paused_by ?? '').trim(),
    }
  }
  return {
    startedBy: String(attrs.analise_started_by ?? '').trim(),
    pausedBy: String(attrs.analise_paused_by ?? '').trim(),
  }
}

export function isOwnOpenAnaliseStage(
  attrs: Record<string, unknown>,
  currentLogin: string,
  stage: OfficeAnaliseStage,
): boolean {
  const login = currentLogin.trim()
  if (!login) return false
  const status = stageWorkflowStatus(attrs, stage)
  if (status !== 'in_progress' && status !== 'paused') return false
  const { startedBy, pausedBy } = stageOwnerLogins(attrs, stage)
  return startedBy === login || pausedBy === login
}

export function isOwnOpenOfficeOrder(
  attrs: Record<string, unknown>,
  currentLogin: string,
): boolean {
  return (
    isOwnOpenAnaliseStage(attrs, currentLogin, 'pre_analise') ||
    isOwnOpenAnaliseStage(attrs, currentLogin, 'analise')
  )
}

export function formatFieldObserved(value: unknown): string {
  if (value == null || value === '') return ''
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  const text = String(value).trim().toLowerCase()
  if (['true', 't', '1', 'yes', 'да'].includes(text)) return 'Да'
  if (['false', 'f', '0', 'no', 'нет'].includes(text)) return 'Нет'
  return String(value)
}

export function isFieldObserved(value: unknown): boolean {
  if (value == null || value === '') return false
  if (typeof value === 'boolean') return value
  const text = String(value).trim().toLowerCase()
  return ['true', 't', '1', 'yes', 'да'].includes(text)
}

export function formatTaskTableUserCell(
  attrs: Record<string, unknown>,
  col: TaskTableColumn,
  users: { login: string; name?: string | null }[] = [],
): string {
  if (
    col.field === 'task_name' ||
    col.field === 'task_number' ||
    col.field === 'key'
  ) {
    const title = String(attrs.task_name ?? attrs.task_number ?? '').trim()
    if (title) return title
    const raw = String(attrs[col.field] ?? '').trim()
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
      ? ''
      : raw
  }
  if (
    col.format === 'user_login' ||
    col.field === 'executor' ||
    col.field === 'executor_name'
  ) {
    const login = String(attrs.executor ?? attrs[col.field] ?? '').trim()
    const apiName = String(attrs.executor_name ?? '').trim()
    return displayUserName(apiName, displayUserNameByLogin(login, users))
  }
  return formatTaskTableCell(attrs[col.field], col.format)
}

export function formatTaskTableCell(value: unknown, format?: TaskTableColumn['format']): string {
  if (format === 'field_observed') return formatFieldObserved(value)
  if (format === 'area_status') return formatAreaStatus(value)
  if (format === 'area_hectares') return formatAreaHectares(value)
  if (value == null || value === '') return ''
  if (format === 'date') {
    const d = new Date(String(value))
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString('ru-RU')
  }
  return String(value)
}

export function taskTableColumnsForSubgroup(
  subgroupName: string | undefined,
  isArea = false,
): TaskTableColumn[] | null {
  if (isArea) return AREA_TASK_TABLE_COLUMNS
  if (!subgroupName) return null
  return TASK_TABLE_COLUMNS[subgroupName] ?? null
}

export function resolveTaskTableColumns(
  subgroupName: string | undefined,
  isArea: boolean,
  featureAttributesList: Record<string, unknown>[],
  showSentAt: boolean,
): TaskTableColumn[] {
  const configured = taskTableColumnsForSubgroup(subgroupName, isArea)
  const cols = configured
    ? [...configured]
    : (() => {
        const names = new Set<string>()
        for (const attrs of featureAttributesList) {
          for (const key of Object.keys(attrs)) {
            if (!key.startsWith('_')) names.add(key)
          }
        }
        const limit = showSentAt ? 5 : 6
        return Array.from(names)
          .sort()
          .slice(0, limit)
          .map((field) => ({ field, label: field }))
      })()

  if (
    !isArea &&
    subgroupName !== FIELD_DATA_SUBGROUP &&
    subgroupName !== OFFICE_ANALYSIS_SUBGROUP &&
    !cols.some((col) => col.field === 'field_observed')
  ) {
    return [FIELD_OBSERVED_COLUMN, ...cols]
  }
  return cols
}

function escapePopupHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function taskExecuteButtonLabel(taskSource: TaskSource): string {
  return taskSource === 'active' ? 'Исполнить задачу' : 'Просмотр задачи'
}

export function buildTaskPopupHtml(
  feature: TaskFeature,
  subgroupName: string,
  taskSource: TaskSource,
): string {
  const isArea = isAreaSource(taskSource)
  const showSentAt = !isArea && taskSource !== 'active'
  const columns = resolveTaskTableColumns(subgroupName, isArea, [feature.attributes], showSentAt)

  const lines: string[] = [`<b>${escapePopupHtml(feature.layer_name)}</b>`]
  if (showSentAt && feature.sent_at) {
    lines.push(
      `<b>Отправлено</b>: ${escapePopupHtml(new Date(feature.sent_at).toLocaleString('ru-RU'))}`,
    )
  }
  for (const col of columns) {
    const value = formatTaskTableUserCell(feature.attributes, col)
    lines.push(`<b>${escapePopupHtml(col.label)}</b>: ${escapePopupHtml(value)}`)
  }
  if (!isArea) {
    const label = taskExecuteButtonLabel(taskSource)
    lines.push(
      `<button type="button" class="btn primary map-popup-execute" data-map-action="execute-task">${escapePopupHtml(label)}</button>`,
    )
  } else {
    lines.push(
      `<button type="button" class="btn map-popup-view-area" data-map-action="view-area-order">Просмотр заказа</button>`,
    )
  }

  return `<div class="map-popup">${lines.join('<br/>')}</div>`
}

export function isAiPhotoContext(subgroupName: string, layerKey?: string): boolean {
  return subgroupName === AI_PHOTO_SUBGROUP || layerKey === AI_PHOTO_LAYER_KEY
}

export function isDitPhotoContext(subgroupName: string, layerKey?: string): boolean {
  return subgroupName === DIT_PHOTO_SUBGROUP || layerKey === DIT_PHOTO_LAYER_KEY
}

export function isLensPhotoContext(subgroupName: string, layerKey?: string): boolean {
  return subgroupName === LENS_PHOTO_SUBGROUP || layerKey === LENS_PHOTO_LAYER_KEY
}

export function aiPhotoUuidFromAttributes(attributes: Record<string, unknown>): string | null {
  const value = attributes.uuid
  if (value == null) return null
  const uuid = String(value).trim()
  return uuid || null
}

export function ditResultIdFromAttributes(attributes: Record<string, unknown>): string | null {
  const value = attributes.result_id
  if (value == null) return null
  const id = String(value).trim()
  return id || null
}

export function lensExternalIdFromAttributes(attributes: Record<string, unknown>): string | null {
  const value = attributes.external_report_id
  if (value == null) return null
  const id = String(value).trim()
  return id || null
}

export interface TaskRecord {
  key: string
  type: string
  photo_uuid?: string | null
  photo_lens?: string | null
  ogh_id?: string | null
  oati_id?: string | null
  earthwork_id?: string | null
  localwork_id?: string | null
  avr_mos_id?: string | null
  dit_result_id?: string | null
  sps?: string | null
  kgs?: string | null
  station_avr?: string | null
  field_observed?: boolean | null
  is_field_data?: boolean | null
  is_office_task?: boolean | null
  user_created?: string[] | null
  user_last_edit?: string[] | null
}

export interface TaskFormFields {
  readonly_fields: string[]
  link_fields: string[]
  labels: Record<string, string>
}

export interface LinkLayerInfo {
  task_column: string
  subgroup_name: string
  layer_key: string
  display_name: string
  source_field: string
}

export interface SelectedTaskContext {
  groupName: string
  subgroupName: string
  feature: TaskFeature
  taskKey?: string
  taskSource: TaskSource
}

export const TASK_SOURCE_LABELS: Record<TaskSource, string> = {
  active: 'Активные',
  field: 'В поле',
  delay: 'Отложенные',
  done_legal: 'Закрыты легальные',
  done_illegal: 'Закрыты нелегальные',
  clear: 'Разрытие отсутствует',
  area: 'Заказы',
}

export function isAreaSource(source: TaskSource): boolean {
  return source === 'area'
}

export function displayUserName(name: string | null | undefined, login: string): string {
  const trimmed = (name ?? '').trim()
  return trimmed || login
}

export function personnelUserLabel(user: {
  name?: string | null
  login: string
  role: string
}): string {
  return `${displayUserName(user.name, user.login)} (${user.role})`
}

export function displayUserNameByLogin(
  login: string | null | undefined,
  users: { login: string; name?: string | null }[],
): string {
  const key = (login ?? '').trim()
  if (!key) return '—'
  const match = users.find((user) => user.login === key)
  return displayUserName(match?.name, key)
}

export function displayAreaOrderTitle(attrs: Record<string, unknown>): string {
  const title = String(attrs.task_number ?? '').trim()
  if (title) return title
  const key = String(attrs.number ?? attrs.key ?? '').trim()
  if (!key) return '—'
  return key.slice(0, 8)
}

export function areaStatusFromAttributes(attrs: Record<string, unknown>): AreaStatus {
  const key = String(attrs.status ?? '').trim().toLowerCase()
  if (
    key === 'free' ||
    key === 'wip' ||
    key === 'wip_field' ||
    key === 'in_pause' ||
    key === 'done'
  ) {
    return key
  }
  return 'free'
}

export type MonitorLevel = 'ok' | 'warn' | 'error'

export interface MonitorDisk {
  path: string
  label: string
  used_bytes: number
  total_bytes: number
  percent: number
}

export interface MonitorHost {
  cpu_percent: number
  loadavg: number[] | null
  memory_used_bytes: number
  memory_total_bytes: number
  memory_percent: number
  disks: MonitorDisk[]
}

export interface MonitorSlowQuery {
  pid: number
  duration_seconds: number
  query: string
}

export interface MonitorDatabase {
  connections: number
  max_connections: number | null
  active_queries: number
  cache_hit_percent: number | null
  size_bytes: number
  slow_queries: MonitorSlowQuery[]
}

export interface MonitorApp {
  status: string
  rss_bytes: number | null
  cpu_percent: number | null
  pool_in_use: number
  pool_max: number
  requests_per_minute: number
  p95_ms: number | null
}

export interface MonitorUnit {
  name: string
  kind: 'docker' | 'systemd'
  state: string
  health: string | null
  cpu_percent: number | null
  memory_bytes: number | null
  started_at: string | null
  uptime_seconds: number | null
  restart_count: number
  level: MonitorLevel
}

export interface MonitorOperation {
  ts: string
  name: string
  status: MonitorLevel
  detail: string
}

export interface MonitorStatus {
  collected_at: string
  overall: MonitorLevel
  warnings: string[]
  host: MonitorHost | null
  database: MonitorDatabase | null
  app: MonitorApp | null
  units: MonitorUnit[]
  operations: MonitorOperation[]
}
