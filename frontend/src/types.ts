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
