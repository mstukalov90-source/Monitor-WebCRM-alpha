export interface MapViewBounds {
  west: number
  south: number
  east: number
  north: number
}

function formatCoord(value: number): string {
  return String(Number(value.toFixed(6)))
}

/** Yandex Maps URL for the current Leaflet viewport (center, zoom, span). */
export function yandexMapsUrlFromView(bounds: MapViewBounds, zoom: number): string {
  const lon = (bounds.west + bounds.east) / 2
  const lat = (bounds.south + bounds.north) / 2
  const dLon = Math.abs(bounds.east - bounds.west)
  const dLat = Math.abs(bounds.north - bounds.south)
  const z = Math.max(0, Math.round(zoom))
  return (
    `https://yandex.ru/maps/?l=map` +
    `&ll=${formatCoord(lon)},${formatCoord(lat)}` +
    `&z=${z}` +
    `&spn=${formatCoord(dLon)},${formatCoord(dLat)}`
  )
}
