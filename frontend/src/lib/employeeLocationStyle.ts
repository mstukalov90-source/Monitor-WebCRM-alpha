import type { CircleMarkerOptions } from 'leaflet'

const COLOR_FRESH = '#198754'
const COLOR_RECENT = '#ffc107'
const COLOR_STALE = '#dc3545'
const COLOR_OLD = '#212529'
const COLOR_SELECTED_STROKE = '#ff6600'

/** Age buckets: <10 green, <30 yellow, <60 red, else black. Missing time → black. */
export function employeeLocationAgeColor(updatedAt: unknown, nowMs: number = Date.now()): string {
  if (updatedAt == null || updatedAt === '') return COLOR_OLD
  const ts = new Date(String(updatedAt)).getTime()
  if (Number.isNaN(ts)) return COLOR_OLD
  const ageMin = (nowMs - ts) / 60_000
  if (ageMin < 10) return COLOR_FRESH
  if (ageMin < 30) return COLOR_RECENT
  if (ageMin < 60) return COLOR_STALE
  return COLOR_OLD
}

export function employeeLocationMarkerStyle(
  updatedAt: unknown,
  selected = false,
): CircleMarkerOptions {
  const fill = employeeLocationAgeColor(updatedAt)
  return {
    radius: selected ? 10 : 8,
    color: selected ? COLOR_SELECTED_STROKE : fill,
    weight: selected ? 3 : 2,
    fillColor: fill,
    fillOpacity: selected ? 1 : 0.85,
  }
}
