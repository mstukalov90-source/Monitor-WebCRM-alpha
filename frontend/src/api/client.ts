import type {
  LayerGroupConfig,
  LinkLayerInfo,
  LinkedTaskFeature,
  MissingLink,
  TaskFormFields,
  TaskRecord,
  TaskResult,
  AreaStatus,
  CollectPlan,
  CollectLayerChunk,
  CollectProgress,
  AiPhotoMeta,
  FieldPhotosResult,
  FieldReportFeature,
  AssignableTask,
  AuthUser,
  DistrictOption,
  PersonnelUser,
  PersonnelUserCreate,
  PersonnelStatistics,
  GeoStatistics,
  WorkflowTargetStatus,
  BulkStatusResult,
  OrderTracksResult,
  EmployeeLocationsResult,
  OatiLetterDraft,
  OatiLetterGeneratePayload,
} from '../types'

const API_BASE = ''

let unauthorizedHandler: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = init?.method === 'POST' ? 45_000 : 30_000,
): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
      ...init,
      signal: controller.signal,
    })
    if (res.status === 401 && !path.startsWith('/api/auth/login')) {
      unauthorizedHandler?.()
    }
    if (!res.ok) {
      const text = await res.text()
      try {
        const parsed = JSON.parse(text) as { detail?: string }
        throw new Error(parsed.detail || text || res.statusText)
      } catch (e) {
        if (e instanceof Error && e.message !== text && !e.message.startsWith('Unexpected token')) {
          throw e
        }
        throw new Error(text || res.statusText)
      }
    }
    if (res.status === 204) {
      return undefined as T
    }
    return res.json() as Promise<T>
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('Превышено время ожидания ответа сервера')
    }
    throw e
  } finally {
    window.clearTimeout(timer)
  }
}

export function fetchAuthMe(): Promise<AuthUser> {
  return request('/api/auth/me')
}

export function login(loginName: string, password: string): Promise<AuthUser> {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login: loginName, password }),
  })
}

export function logout(): Promise<void> {
  return request('/api/auth/logout', { method: 'POST' })
}

export function fetchLayersConfig(): Promise<{ groups: LayerGroupConfig[] }> {
  return request('/api/config/layers')
}

export function fetchDistricts(): Promise<{ districts: string[] }> {
  return request('/api/districts')
}

export function fetchGeoJson(layerKey: string, bbox: string, limit = 2000): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams({ bbox, limit: String(limit) })
  return request(`/api/geojson/${encodeURIComponent(layerKey)}?${params}`)
}

export function collectTasks(rayon: string, applyDateFilter: boolean): Promise<TaskResult> {
  return request('/api/tasks/collect', {
    method: 'POST',
    body: JSON.stringify({ rayon, apply_date_filter: applyDateFilter }),
  })
}

export function fetchCollectPlan(rayon: string, applyDateFilter: boolean): Promise<CollectPlan> {
  const params = new URLSearchParams({
    rayon,
    apply_date_filter: String(applyDateFilter),
  })
  return request(`/api/tasks/collect/plan?${params}`)
}

export function collectTasksLayer(
  rayon: string,
  applyDateFilter: boolean,
  layer: {
    group_name: string
    subgroup_name: string
    layer_key: string
  },
): Promise<CollectLayerChunk> {
  return request(
    '/api/tasks/collect/layer',
    {
      method: 'POST',
      body: JSON.stringify({
        rayon,
        apply_date_filter: applyDateFilter,
        group_name: layer.group_name,
        subgroup_name: layer.subgroup_name,
        layer_key: layer.layer_key,
      }),
    },
    60_000,
  )
}

export async function collectTasksByLayers(
  rayon: string,
  applyDateFilter: boolean,
  onProgress?: (progress: CollectProgress) => void,
): Promise<TaskResult> {
  const plan = await fetchCollectPlan(rayon, applyDateFilter)

  const total = plan.layers.length
  const layerErrors: string[] = [...plan.errors]
  for (let index = 0; index < plan.layers.length; index += 1) {
    const layer = plan.layers[index]
    onProgress?.({
      current: index + 1,
      total,
      layerName: layer.layer_name,
    })
    const chunk = await collectTasksLayer(rayon, applyDateFilter, layer)
    if (chunk.errors.length) {
      layerErrors.push(...chunk.errors)
    }
  }

  const active = await fetchActiveTasks(rayon, applyDateFilter)
  if (layerErrors.length) {
    active.errors = [...active.errors, ...layerErrors]
  }
  return active
}

export function fetchActiveTasks(rayon: string, applyDateFilter: boolean): Promise<TaskResult> {
  const params = new URLSearchParams({
    rayon,
    apply_date_filter: String(applyDateFilter),
  })
  return request(`/api/tasks/active?${params}`, undefined, 90_000)
}

export function fetchSnapshotTasks(
  rayon: string,
  source: 'field' | 'done_legal' | 'done_illegal' | 'clear',
): Promise<TaskResult> {
  const params = new URLSearchParams({ rayon, source })
  return request(`/api/tasks/snapshot?${params}`, undefined, 90_000)
}

export function fetchTasksArea(rayon: string, status?: AreaStatus): Promise<TaskResult> {
  const params = new URLSearchParams({ rayon })
  if (status) params.set('status', status)
  return request(`/api/tasks/area?${params}`)
}

export function sendAreaToSurvey(key: string): Promise<{ status: string }> {
  return request(`/api/crm/tasks-area/${encodeURIComponent(key)}/send-to-survey`, {
    method: 'POST',
  })
}

export function releaseAreaFromSurvey(key: string): Promise<{ status: string }> {
  return request(`/api/crm/tasks-area/${encodeURIComponent(key)}/release-from-survey`, {
    method: 'POST',
  })
}

export function completeAreaSurvey(key: string): Promise<{ status: string }> {
  return request(`/api/crm/tasks-area/${encodeURIComponent(key)}/complete-survey`, {
    method: 'POST',
  })
}

export function startAreaAnalise(key: string): Promise<{ status: string }> {
  return request(`/api/crm/tasks-area/${encodeURIComponent(key)}/start-analise`, {
    method: 'POST',
  })
}

export function pauseAreaAnalise(key: string): Promise<{ status: string }> {
  return request(`/api/crm/tasks-area/${encodeURIComponent(key)}/pause-analise`, {
    method: 'POST',
  })
}

export function completeAreaAnalise(key: string): Promise<{ status: string }> {
  return request(`/api/crm/tasks-area/${encodeURIComponent(key)}/complete-analise`, {
    method: 'POST',
  })
}

export function fetchTask(key: string): Promise<TaskRecord> {
  return request(`/api/tasks/${key}`)
}

export function fetchTaskFormFields(
  key: string,
  groupName: string,
  subgroupName: string,
): Promise<TaskFormFields> {
  const params = new URLSearchParams({ group_name: groupName, subgroup_name: subgroupName })
  return request(`/api/tasks/${key}/form-fields?${params}`)
}

export function updateTask(key: string, data: Partial<TaskRecord>): Promise<TaskRecord> {
  return request(`/api/tasks/${key}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export interface CreateOfficeTaskPayload {
  geometry: GeoJSON.Point
  area_task_key: string
  link_prefill?: Record<string, string> | null
}

export function createOfficeTask(payload: CreateOfficeTaskPayload): Promise<TaskRecord> {
  return request('/api/tasks/office', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function sendTaskToField(
  key: string,
  officeComment: string | null | undefined,
  rayon: string,
): Promise<{ status: string }> {
  return request(`/api/tasks/${key}/send-to-field`, {
    method: 'POST',
    body: JSON.stringify({
      rayon,
      office_comment: officeComment?.trim() || null,
    }),
  })
}

export function closeTaskLegal(key: string, rayon?: string): Promise<{ status: string }> {
  return request(`/api/tasks/${key}/close-legal`, {
    method: 'POST',
    body: JSON.stringify({ rayon: rayon || null }),
  })
}

export function closeTaskIllegal(key: string, rayon?: string): Promise<{ status: string }> {
  return request(`/api/tasks/${key}/close-illegal`, {
    method: 'POST',
    body: JSON.stringify({ rayon: rayon || null }),
  })
}

export function markDisruptionAbsent(key: string, rayon?: string): Promise<{ status: string }> {
  return request(`/api/tasks/${key}/disruption-absent`, {
    method: 'POST',
    body: JSON.stringify({ rayon: rayon || null }),
  })
}

export function returnTaskToActive(key: string): Promise<{ status: string }> {
  return request(`/api/tasks/${key}/return-to-active`, { method: 'POST' })
}

export function fetchLinkLayers(columns: string[]): Promise<{ layers: LinkLayerInfo[] }> {
  const params = new URLSearchParams({ columns: columns.join(',') })
  return request(`/api/crm/link-layers?${params}`)
}

export function lookupFeature(
  layerKey: string,
  sourceField: string,
  businessId: string,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({
    layer_key: layerKey,
    source_field: sourceField,
    business_id: businessId,
  })
  return request(`/api/features/lookup?${params}`)
}

export function fetchAllTasksAreaGeoJson(status?: AreaStatus): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  const qs = params.toString()
  return request(`/api/crm/tasks-area${qs ? `?${qs}` : ''}`)
}

export function fetchTasksAreaGeoJson(
  rayon: string,
  status?: AreaStatus,
): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams({ rayon })
  if (status) params.set('status', status)
  return request(`/api/crm/tasks-area?${params}`)
}

export function fetchLinkedFeatures(
  key: string,
  groupName: string,
): Promise<{ linked_features: LinkedTaskFeature[]; missing_links: MissingLink[] }> {
  const params = new URLSearchParams({ group_name: groupName })
  return request(`/api/tasks/${key}/linked-features?${params}`)
}

export function lookupTaskByFeature(
  subgroupName: string,
  attributes: Record<string, unknown>,
  layerKey?: string,
): Promise<TaskRecord> {
  const params = new URLSearchParams({
    subgroup_name: subgroupName,
    attributes: JSON.stringify(attributes),
  })
  if (layerKey) params.set('layer_key', layerKey)
  return request(`/api/tasks/lookup/by-feature?${params}`)
}

export function fetchAiPhotoMeta(uuid: string): Promise<AiPhotoMeta> {
  return request(`/api/photos/ai/${encodeURIComponent(uuid)}/meta`)
}

export function aiPhotoImageUrl(uuid: string): string {
  return `/api/photos/ai/${encodeURIComponent(uuid)}/image`
}

export function fetchFieldPhotos(
  taskKey: string,
  options?: { reportId?: number | null; reportTask?: string | null },
): Promise<FieldPhotosResult> {
  const params = new URLSearchParams()
  if (options?.reportId != null) params.set('report_id', String(options.reportId))
  else if (options?.reportTask) params.set('report_task', options.reportTask)
  const qs = params.toString()
  return request(
    `/api/tasks/${encodeURIComponent(taskKey)}/field-photos${qs ? `?${qs}` : ''}`,
  )
}

export function fetchFieldReports(
  taskKey: string,
): Promise<{ reports: FieldReportFeature[] }> {
  return request(`/api/tasks/${encodeURIComponent(taskKey)}/field-reports`)
}

export function fetchOatiLetterDraft(
  taskKey: string,
  reportId: number,
): Promise<OatiLetterDraft> {
  return request(
    `/api/tasks/${encodeURIComponent(taskKey)}/field-reports/${reportId}/letter-draft`,
  )
}

export async function generateOatiLetter(
  taskKey: string,
  reportId: number,
  payload: OatiLetterGeneratePayload,
): Promise<{ blob: Blob; filename: string; fid: number | null }> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 120_000)
  try {
    const res = await fetch(
      `${API_BASE}/api/tasks/${encodeURIComponent(taskKey)}/field-reports/${reportId}/letters`,
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
    )
    if (res.status === 401) {
      unauthorizedHandler?.()
    }
    if (!res.ok) {
      const text = await res.text()
      try {
        const parsed = JSON.parse(text) as { detail?: string }
        throw new Error(parsed.detail || text || res.statusText)
      } catch (e) {
        if (e instanceof Error && e.message !== text && !e.message.startsWith('Unexpected token')) {
          throw e
        }
        throw new Error(text || res.statusText)
      }
    }
    const blob = await res.blob()
    const fidHeader = res.headers.get('X-Oati-Letter-Fid')
    const fid = fidHeader ? Number(fidHeader) : null
    let filename = fid != null && !Number.isNaN(fid) ? `Письмо_ОАТИ_${fid}.docx` : 'Письмо_ОАТИ.docx'
    const disposition = res.headers.get('Content-Disposition')
    if (disposition) {
      const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
      const plainMatch = /filename="?([^";]+)"?/i.exec(disposition)
      if (utfMatch?.[1]) {
        try {
          filename = decodeURIComponent(utfMatch[1])
        } catch {
          filename = utfMatch[1]
        }
      } else if (plainMatch?.[1]) {
        filename = plainMatch[1]
      }
    }
    return { blob, filename, fid: fid != null && !Number.isNaN(fid) ? fid : null }
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('Превышено время ожидания ответа сервера')
    }
    throw e
  } finally {
    window.clearTimeout(timer)
  }
}

export function fieldPhotoImageUrl(filePath: string): string {
  const name = filePath.split(/[/\\]/).pop() ?? filePath
  return `/api/photos/field/${encodeURIComponent(name)}/image`
}

export function fetchPersonnelUsers(): Promise<PersonnelUser[]> {
  return request('/api/personnel/users')
}

export function createPersonnelUser(data: PersonnelUserCreate): Promise<PersonnelUser> {
  return request('/api/personnel/users', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function fetchPersonnelDistricts(): Promise<DistrictOption[]> {
  return request('/api/personnel/districts')
}

export function updatePersonnelUserWorkZones(
  uuid: string,
  workZones: number[],
): Promise<PersonnelUser> {
  return request(`/api/personnel/users/${encodeURIComponent(uuid)}`, {
    method: 'PATCH',
    body: JSON.stringify({ work_zones: workZones }),
  })
}

const PERSONNEL_TASKS_TIMEOUT_MS = 90_000
const PERSONNEL_BULK_TIMEOUT_MS = 300_000

function personnelBulkTimeout(taskCount: number): number {
  return Math.max(PERSONNEL_BULK_TIMEOUT_MS, taskCount * 5_000)
}

export function fetchPersonnelActiveTasks(params: {
  rayon?: string
}): Promise<AssignableTask[]> {
  const q = new URLSearchParams()
  if (params.rayon) q.set('rayon', params.rayon)
  const qs = q.toString()
  return request(`/api/personnel/tasks/active${qs ? `?${qs}` : ''}`, undefined, PERSONNEL_TASKS_TIMEOUT_MS)
}

export function fetchPersonnelClearTasks(params: {
  rayon?: string
}): Promise<AssignableTask[]> {
  const q = new URLSearchParams()
  if (params.rayon) q.set('rayon', params.rayon)
  const qs = q.toString()
  return request(`/api/personnel/tasks/clear${qs ? `?${qs}` : ''}`, undefined, PERSONNEL_TASKS_TIMEOUT_MS)
}

export function fetchPersonnelFieldTasks(params: {
  rayon?: string
  executor?: string
  unassignedOnly?: boolean
}): Promise<AssignableTask[]> {
  const q = new URLSearchParams()
  if (params.rayon) q.set('rayon', params.rayon)
  if (params.executor) q.set('executor', params.executor)
  if (params.unassignedOnly) q.set('unassigned_only', 'true')
  const qs = q.toString()
  return request(`/api/personnel/tasks/field${qs ? `?${qs}` : ''}`, undefined, PERSONNEL_TASKS_TIMEOUT_MS)
}

export function fetchPersonnelAreaTasks(params: {
  rayon?: string
  status?: string
  executor?: string
  unassignedOnly?: boolean
}): Promise<AssignableTask[]> {
  const q = new URLSearchParams()
  if (params.rayon) q.set('rayon', params.rayon)
  if (params.status) q.set('status', params.status)
  if (params.executor) q.set('executor', params.executor)
  if (params.unassignedOnly) q.set('unassigned_only', 'true')
  const qs = q.toString()
  return request(`/api/personnel/tasks/area${qs ? `?${qs}` : ''}`, undefined, PERSONNEL_TASKS_TIMEOUT_MS)
}

export function bulkChangePersonnelTaskStatus(
  taskKeys: string[],
  targetStatus: WorkflowTargetStatus,
  rayon?: string,
): Promise<BulkStatusResult> {
  return request(
    '/api/personnel/tasks/bulk-status',
    {
      method: 'POST',
      body: JSON.stringify({
        task_keys: taskKeys,
        target_status: targetStatus,
        rayon: rayon || null,
      }),
    },
    personnelBulkTimeout(taskKeys.length),
  )
}

export function bulkAssignPersonnelTasks(
  table: 'field' | 'area',
  keys: string[],
  executor: string | null,
): Promise<{ updated: number; not_found: number }> {
  return request(
    '/api/personnel/tasks/bulk-assign',
    {
      method: 'POST',
      body: JSON.stringify({ table, keys, executor }),
    },
    personnelBulkTimeout(keys.length),
  )
}

export function assignFieldTaskExecutor(
  key: string,
  executor: string | null,
): Promise<{ status: string }> {
  return request(`/api/personnel/tasks/field/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    body: JSON.stringify({ executor }),
  })
}

export function assignAreaTaskExecutor(
  key: string,
  executor: string | null,
): Promise<{ status: string }> {
  return request(`/api/personnel/tasks/area/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    body: JSON.stringify({ executor }),
  })
}

export function updateAreaTaskNumber(
  key: string,
  taskNumber: string | null,
): Promise<{ status: string }> {
  return request(`/api/personnel/tasks/area/${encodeURIComponent(key)}/task-number`, {
    method: 'PATCH',
    body: JSON.stringify({ task_number: taskNumber }),
  })
}

export function lookupFieldSnapshot(
  taskKey: string,
): Promise<{ snapshot_key: string; executor: string | null }> {
  const params = new URLSearchParams({ task_key: taskKey })
  return request(`/api/personnel/tasks/field/lookup?${params}`)
}

export function fetchPersonnelStatistics(params: {
  dateFrom: string
  dateTo: string
  userRole?: 'field' | 'office'
  objectType?: 'task' | 'order'
  userLogin?: string
}): Promise<PersonnelStatistics> {
  const qs = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  })
  if (params.userRole) qs.set('user_role', params.userRole)
  if (params.objectType) qs.set('object_type', params.objectType)
  if (params.userLogin) qs.set('user_login', params.userLogin)
  return request(`/api/personnel/statistics?${qs}`)
}

export function fetchPersonnelGeoStatistics(params: {
  dateFrom: string
  dateTo: string
  userRole?: 'field' | 'office'
  objectType?: 'task' | 'order'
  userLogin?: string
}): Promise<GeoStatistics> {
  const qs = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  })
  if (params.userRole) qs.set('user_role', params.userRole)
  if (params.objectType) qs.set('object_type', params.objectType)
  if (params.userLogin) qs.set('user_login', params.userLogin)
  return request(`/api/personnel/statistics/geo?${qs}`)
}

export function fetchOrderTracks(rayon: string): Promise<OrderTracksResult> {
  const qs = new URLSearchParams({ rayon })
  return request(`/api/order-tracks?${qs}`)
}

export function fetchEmployeeLocations(rayon?: string): Promise<EmployeeLocationsResult> {
  const qs = rayon ? new URLSearchParams({ rayon }) : ''
  return request(`/api/employee-locations${qs ? `?${qs}` : ''}`)
}
