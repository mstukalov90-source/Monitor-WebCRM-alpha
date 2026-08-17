import L from 'leaflet'

export function parsePhotoAzimuth(value: unknown): number | null {
  if (value == null || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return null
  return ((parsed % 360) + 360) % 360
}

export function photoAzimuthMarker(
  latlng: L.LatLngExpression,
  azimuthDeg: number,
  color: string,
): L.Marker {
  const html =
    `<div class="photo-azimuth-arrow" style="color:${color};transform:rotate(${azimuthDeg}deg)">` +
    '<svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">' +
    '<path d="M16 3 L20 14 L16 11.5 L12 14 Z" fill="currentColor"/>' +
    '<path d="M16 11 L16 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/>' +
    '</svg></div>'

  return L.marker(latlng, {
    icon: L.divIcon({
      className: 'photo-azimuth-icon',
      html,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    }),
    interactive: false,
    keyboard: false,
  })
}

export function pointLayerWithAzimuth(
  latlng: L.LatLngExpression,
  circle: L.CircleMarker,
  azimuthDeg: number | null,
  color: string,
): L.Layer {
  if (azimuthDeg == null) return circle
  return L.featureGroup([circle, photoAzimuthMarker(latlng, azimuthDeg, color)])
}
