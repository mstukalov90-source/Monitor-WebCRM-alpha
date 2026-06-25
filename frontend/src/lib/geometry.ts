type Position = GeoJSON.Position

export function extractPolygonRings(geometry: GeoJSON.Geometry): Position[][] {
  if (geometry.type === 'Polygon') {
    return geometry.coordinates
  }
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.flatMap((polygon) => polygon)
  }
  return []
}

/** Ray-casting point-in-polygon test (first ring = outer boundary). */
export function pointInPolygon(lngLat: Position, rings: Position[][]): boolean {
  if (rings.length === 0) return false
  const [lng, lat] = lngLat
  const outer = rings[0]
  if (!outer || outer.length < 3) return false

  let inside = false
  for (let i = 0, j = outer.length - 1; i < outer.length; j = i++) {
    const [xi, yi] = outer[i]
    const [xj, yj] = outer[j]
    const intersects = yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersects) inside = !inside
  }
  return inside
}

function firstCoordinate(geometry: GeoJSON.Geometry): Position | null {
  switch (geometry.type) {
    case 'Point':
      return geometry.coordinates
    case 'MultiPoint':
      return geometry.coordinates[0] ?? null
    case 'LineString':
      return geometry.coordinates[0] ?? null
    case 'MultiLineString':
      return geometry.coordinates[0]?.[0] ?? null
    case 'Polygon':
      return geometry.coordinates[0]?.[0] ?? null
    case 'MultiPolygon':
      return geometry.coordinates[0]?.[0]?.[0] ?? null
    default:
      return null
  }
}

export function geometryInsideArea(
  geometry: GeoJSON.Geometry | null | undefined,
  areaGeometry: GeoJSON.Geometry,
): boolean {
  if (!geometry) return false
  const rings = extractPolygonRings(areaGeometry)
  if (rings.length === 0) return false

  if (geometry.type === 'Point') {
    return pointInPolygon(geometry.coordinates, rings)
  }
  if (geometry.type === 'MultiPoint') {
    return geometry.coordinates.some((coord) => pointInPolygon(coord, rings))
  }

  const coord = firstCoordinate(geometry)
  return coord ? pointInPolygon(coord, rings) : false
}
