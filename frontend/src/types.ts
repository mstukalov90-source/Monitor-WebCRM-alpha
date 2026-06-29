export type UserRole = 'admin' | 'field' | 'office' | 'manager'

export interface AuthUser {
  login: string
  role: UserRole
  work_zones: number[]
  allowed_task_sources: TaskSource[]
  default_task_source: TaskSource
  can_collect: boolean
  can_manage_personnel: boolean
  can_create_users: boolean
}

export interface PersonnelUserCreate {
  login: string
  password: string
  role: UserRole
  work_zones: number[]
}

export interface PersonnelUser {
  uuid: string
  login: string
  role: UserRole
  work_zones: number[]
  district_names: string[]
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
  tasks_completed: number
  orders_completed: number
  tasks_created: number
  period_from: string | null
  period_to: string | null
}

export interface OfficeStatisticsBreakdown {
  user_login: string
  user_role: string
  object_type: string
  action: string
  action_count: number
  period_from: string | null
  period_to: string | null
}

export interface PersonnelStatistics {
  field_summary: FieldStatisticsSummary[]
  office_breakdown: OfficeStatisticsBreakdown[]
  date_from: string
  date_to: string
  scope: 'all' | 'self'
}

export type AppView = 'workspace' | 'personnel' | 'statistics'

export const HOOD_BOUNDARIES_DISPLAY_NAME = 'Границы районов'
export const DISTRICT_RAYON_FIELD = 'rayon'
export const DISTRICT_OKRUG_FIELD = 'okrug_shor'
export const EXCLUDED_OKRUG_SHORT = ['НАО', 'ТАО'] as const
/** Bbox Москвы и ближайшей области: minLon,minLat,maxLon,maxLat */
export const MOSCOW_MAP_BBOX = '36.8,55.4,38.2,56.1'

export function normalizeRayonName(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
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
  | 'done_legal'
  | 'done_illegal'
  | 'clear'
  | 'area'

export type TaskFilterSelection = '' | TaskSource

export const TASK_FILTER_NONE = '' as const
export const TASK_FILTER_LABEL = 'Задачи'

export type AreaStatus = 'free' | 'wip' | 'done'

export const AREA_STATUS_COLORS: Record<AreaStatus, string> = {
  free: '#ff9800',
  wip: '#fdd835',
  done: '#43a047',
}

export const TASK_SECTION_TASK_SOURCES: TaskSource[] = [
  'active',
  'field',
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
  missingLinks?: MissingLink[]
  popup?: TaskHighlightPopup
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
}

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
}

export const AI_PHOTO_SUBGROUP = 'Фото после обработки ИИ'
export const AI_PHOTO_LAYER_KEY = 'фотографии_после_обработки_ии'
export const LENS_PHOTO_SUBGROUP = 'Фото разрытий и строек'
export const OGH_DISRUPTION_SUBGROUP = 'Разрытия из полигонов ОГХ'
export const FIELD_DATA_SUBGROUP = 'Полевые данные'
export const FIELD_DATA_LAYER_KEY = 'field_data'
export const OFFICE_ANALYSIS_SUBGROUP = 'Задачи из камерального анализа'
export const OFFICE_DATA_LAYER_KEY = 'office_data'
export const OATI_ORDERS_SUBGROUP = 'Ордера ОАТИ'
export const EARTHWORK_SUBGROUP = 'Уведомления на земляные работы'
export const AVR_SUBGROUP = 'Аварийно-восстановительные работы'
export const LOCAL_REPAIR_SUBGROUP = 'Текущие локальные ремонты'

export interface TaskTableColumn {
  field: string
  label: string
  format?: 'date' | 'field_observed' | 'area_status' | 'area_hectares'
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
  [LENS_PHOTO_SUBGROUP]: [
    { field: 'comment', label: 'Комментарий' },
    { field: 'created_at', label: 'Дата съёмки', format: 'date' },
  ],
  [OGH_DISRUPTION_SUBGROUP]: [
    { field: 'loaded_at', label: 'Дата загрузки', format: 'date' },
  ],
  [OATI_ORDERS_SUBGROUP]: [
    { field: 'customer_construction', label: 'Заказчик' },
    { field: 'order_number', label: 'Номер ордера' },
  ],
  [EARTHWORK_SUBGROUP]: [
    { field: 'executor', label: 'Заказчик' },
    { field: 'registration_number_notifications', label: 'Номер уведомления' },
  ],
  [AVR_SUBGROUP]: [
    { field: 'balanceholder', label: 'Заказчик' },
    { field: 'lead_of_work', label: 'Исполнитель' },
    { field: 'em_call_reg_num', label: 'Номер аварийного вызова' },
  ],
  [LOCAL_REPAIR_SUBGROUP]: [
    { field: 'customer', label: 'Заказчик' },
    { field: 'global_id', label: 'Номер data.mos' },
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

export const AREA_TASK_TABLE_COLUMNS: TaskTableColumn[] = [
  { field: 'status', label: 'Статус', format: 'area_status' },
  { field: 'task_number', label: 'Номер задачи' },
  { field: 'area', label: 'Площадь', format: 'area_hectares' },
  { field: 'date_survey', label: 'Дата обследования', format: 'date' },
  { field: 'executor', label: 'Исполнитель' },
  { field: 'analise', label: 'Анализ', format: 'field_observed' },
]

export const AREA_TASK_STATUS_LABELS: Record<AreaStatus, string> = {
  free: 'Свободный заказ',
  wip: 'На обследовании',
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
    const value = formatTaskTableCell(feature.attributes[col.field], col.format)
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

export function aiPhotoUuidFromAttributes(attributes: Record<string, unknown>): string | null {
  const value = attributes.uuid
  if (value == null) return null
  const uuid = String(value).trim()
  return uuid || null
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
  done_legal: 'Закрыты легальные',
  done_illegal: 'Закрыты нелегальные',
  clear: 'Разрытие отсутствует',
  area: 'Заказы',
}

export function isAreaSource(source: TaskSource): boolean {
  return source === 'area'
}

export function areaStatusFromAttributes(attrs: Record<string, unknown>): AreaStatus {
  const key = String(attrs.status ?? '').trim().toLowerCase()
  if (key === 'free' || key === 'wip' || key === 'done') return key
  return 'free'
}
