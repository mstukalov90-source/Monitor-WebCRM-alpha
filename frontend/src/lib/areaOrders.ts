import type { TaskFeature } from '../types'
import {
  analiseWorkflowStatus,
  analiseWorkflowStatusClass,
  areaStatusFromAttributes,
  formatAnaliseWorkflowStatus,
  formatAreaStatus,
  normalizeRayonName,
} from '../types'

export interface AreaOrdersByRayon {
  rayon: string
  orders: TaskFeature[]
}

export function geoJsonToAreaTaskFeatures(geojson: GeoJSON.FeatureCollection): TaskFeature[] {
  return (geojson.features ?? []).map((item) => {
    const props = { ...(item.properties ?? {}) }
    return {
      layer_name: 'Площадные заказы',
      layer_key: 'tasks_area',
      attributes: props,
      geometry: item.geometry ?? null,
      task_key: String(props.key ?? item.id ?? ''),
    }
  })
}

export function groupAreaOrdersByRayon(orders: TaskFeature[]): AreaOrdersByRayon[] {
  const byRayon = new Map<string, TaskFeature[]>()

  for (const order of orders) {
    const rayon = normalizeRayonName(String(order.attributes.rayon ?? '')) || '—'
    const bucket = byRayon.get(rayon)
    if (bucket) bucket.push(order)
    else byRayon.set(rayon, [order])
  }

  return [...byRayon.entries()]
    .sort(([a], [b]) => a.localeCompare(b, 'ru'))
    .map(([rayon, rayonOrders]) => ({
      rayon,
      orders: [...rayonOrders].sort((a, b) =>
        String(a.attributes.task_number ?? '').localeCompare(
          String(b.attributes.task_number ?? ''),
          'ru',
        ),
      ),
    }))
}

export function areaOrderDisplayName(attrs: Record<string, unknown>): string {
  const taskNumber = attrs.task_number
  if (taskNumber != null && String(taskNumber).trim() !== '') {
    return String(taskNumber).trim()
  }
  return '—'
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Popup HTML for a district: same content as the sidebar area-orders list for that rayon. */
export function buildDistrictOrdersPopupHtml(
  districtName: string,
  orders: TaskFeature[],
): string {
  const title = escapeHtml(districtName || 'Район')
  if (!orders.length) {
    return (
      `<div class="district-map-popup">` +
      `<strong class="district-map-popup-title">${title}</strong>` +
      `<p class="muted small">Нет площадных заказов</p>` +
      `</div>`
    )
  }

  const items = orders
    .map((order) => {
      const attrs = order.attributes
      const name = escapeHtml(areaOrderDisplayName(attrs))
      const surveyStatus = areaStatusFromAttributes(attrs)
      const surveyLabel = escapeHtml(formatAreaStatus(surveyStatus) || '—')
      const workflow = analiseWorkflowStatus(attrs)
      const analiseLabel = escapeHtml(formatAnaliseWorkflowStatus(attrs))
      const analiseClass = analiseWorkflowStatusClass(workflow)
      return (
        `<li class="district-orders-item">` +
        `<span class="district-orders-name" title="${name}">${name}</span>` +
        `<span class="district-orders-statuses">` +
        `<span class="area-survey-status area-survey-status-${surveyStatus}" ` +
        `title="Полевое обследование: ${surveyLabel}">${surveyLabel}</span>` +
        `<span class="area-analise-status ${analiseClass}" ` +
        `title="Анализ: ${analiseLabel}">${analiseLabel}</span>` +
        `</span>` +
        `</li>`
      )
    })
    .join('')

  return (
    `<div class="district-map-popup">` +
    `<strong class="district-map-popup-title">${title}</strong>` +
    `<p class="district-map-popup-subtitle muted small">Площадные заказы: ${orders.length}</p>` +
    `<ul class="district-orders-items">${items}</ul>` +
    `</div>`
  )
}

export function ordersForRayon(
  groups: AreaOrdersByRayon[],
  rayonName: string,
): TaskFeature[] {
  const key = normalizeRayonName(rayonName)
  const group = groups.find((g) => normalizeRayonName(g.rayon) === key)
  return group?.orders ?? []
}
