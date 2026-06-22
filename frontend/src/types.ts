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
  | 'area_free'
  | 'area_wip'
  | 'area_done'

export type AreaStatus = 'free' | 'wip' | 'done'

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

export interface TaskHighlight {
  primary?: GeoJSON.Geometry | null
  linked: LinkedTaskFeature[]
  missingLinks?: MissingLink[]
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

export const AI_PHOTO_SUBGROUP = 'Фото после обработки ИИ'
export const AI_PHOTO_LAYER_KEY = 'фотографии_после_обработки_ии'
export const LENS_PHOTO_SUBGROUP = 'Фото разрытий и строек'
export const OGH_DISRUPTION_SUBGROUP = 'Разрытия из полигонов ОГХ'
export const OATI_ORDERS_SUBGROUP = 'Ордера ОАТИ'
export const EARTHWORK_SUBGROUP = 'Уведомления на земляные работы'
export const AVR_SUBGROUP = 'Аварийно-восстановительные работы'
export const LOCAL_REPAIR_SUBGROUP = 'Текущие локальные ремонты'

export interface TaskTableColumn {
  field: string
  label: string
  format?: 'date' | 'field_observed'
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
}

export const AREA_TASK_TABLE_COLUMNS: TaskTableColumn[] = [
  { field: 'date_survey', label: 'Дата обследования', format: 'date' },
]

export function formatFieldObserved(value: unknown): string {
  if (value == null || value === '') return ''
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  const text = String(value).trim().toLowerCase()
  if (['true', 't', '1', 'yes', 'да'].includes(text)) return 'Да'
  if (['false', 'f', '0', 'no', 'нет'].includes(text)) return 'Нет'
  return String(value)
}

export function formatTaskTableCell(value: unknown, format?: TaskTableColumn['format']): string {
  if (format === 'field_observed') return formatFieldObserved(value)
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

  if (!isArea && !cols.some((col) => col.field === 'field_observed')) {
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
  area_free: 'Площадные — свободные',
  area_wip: 'Площадные — на обследовании',
  area_done: 'Площадные — завершённые',
}

export function isAreaSource(source: TaskSource): boolean {
  return source.startsWith('area_')
}

export function areaStatusFromSource(source: TaskSource): AreaStatus | null {
  if (source === 'area_free') return 'free'
  if (source === 'area_wip') return 'wip'
  if (source === 'area_done') return 'done'
  return null
}
