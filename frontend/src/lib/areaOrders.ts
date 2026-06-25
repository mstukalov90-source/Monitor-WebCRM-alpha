import type { TaskFeature } from '../types'
import { normalizeRayonName } from '../types'

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
