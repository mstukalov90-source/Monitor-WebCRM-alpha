type Position = GeoJSON.Position

/** All rings from a Polygon, or flattened rings from a MultiPolygon (for display/iteration). */
export function extractPolygonRings(geometry: GeoJSON.Geometry): Position[][] {
  if (geometry.type === 'Polygon') {
    return geometry.coordinates
  }
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.flatMap((polygon) => polygon)
  }
  return []
}

/** Ray-casting test for a single closed ring. */
function pointInRing(lngLat: Position, ring: Position[]): boolean {
  if (ring.length < 3) return false
  const [lng, lat] = lngLat

  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    const intersects = yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersects) inside = !inside
  }
  return inside
}

/**
 * Point-in-polygon for one GeoJSON Polygon rings array:
 * first ring = outer boundary, subsequent rings = holes.
 */
export function pointInPolygon(lngLat: Position, rings: Position[][]): boolean {
  if (rings.length === 0) return false
  const outer = rings[0]
  if (!outer || !pointInRing(lngLat, outer)) return false

  for (let i = 1; i < rings.length; i++) {
    const hole = rings[i]
    if (hole && pointInRing(lngLat, hole)) return false
  }
  return true
}

function pointInAreaGeometry(lngLat: Position, areaGeometry: GeoJSON.Geometry): boolean {
  if (areaGeometry.type === 'Polygon') {
    return pointInPolygon(lngLat, areaGeometry.coordinates)
  }
  if (areaGeometry.type === 'MultiPolygon') {
    return areaGeometry.coordinates.some((polygon) => pointInPolygon(lngLat, polygon))
  }
  return false
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
  if (areaGeometry.type !== 'Polygon' && areaGeometry.type !== 'MultiPolygon') {
    return false
  }

  if (geometry.type === 'Point') {
    return pointInAreaGeometry(geometry.coordinates, areaGeometry)
  }
  if (geometry.type === 'MultiPoint') {
    return geometry.coordinates.some((coord) => pointInAreaGeometry(coord, areaGeometry))
  }

  const coord = firstCoordinate(geometry)
  return coord ? pointInAreaGeometry(coord, areaGeometry) : false
}
