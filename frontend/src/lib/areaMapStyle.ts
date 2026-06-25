import L from 'leaflet'
import type { AreaStatus } from '../types'
import { AREA_STATUS_COLORS } from '../types'

const HATCH_GREEN_ID = 'area-hatch-green'
const HATCH_RED_ID = 'area-hatch-red'
const HATCH_DEFS_ID = 'area-hatch-defs'

const preparedSvgs = new WeakSet<SVGSVGElement>()

export function parseAreaAnalise(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === 'boolean') return value
  const text = String(value).trim().toLowerCase()
  return ['true', 't', '1', 'yes', 'да'].includes(text)
}

export function areaStatusFromAttributes(attrs: Record<string, unknown>): AreaStatus {
  const key = String(attrs.status ?? '').trim().toLowerCase()
  if (key === 'free' || key === 'wip' || key === 'done') return key
  return 'free'
}

export function areaBasePathStyle(attrs: Record<string, unknown>): L.PathOptions {
  const color = AREA_STATUS_COLORS[areaStatusFromAttributes(attrs)]
  return {
    color,
    weight: 2,
    fillColor: color,
    fillOpacity: 0.35,
  }
}

export function areaOutlinePathStyle(attrs: Record<string, unknown>): L.PathOptions {
  const color = AREA_STATUS_COLORS[areaStatusFromAttributes(attrs)]
  return {
    color,
    weight: 2,
    fillOpacity: 0,
    fill: false,
  }
}

export function areaHatchPathStyle(attrs: Record<string, unknown>): L.PathOptions {
  const hatchId = parseAreaAnalise(attrs.analise) ? HATCH_GREEN_ID : HATCH_RED_ID
  return {
    color: 'transparent',
    weight: 0,
    fillColor: `url(#${hatchId})`,
    fillOpacity: 1,
  }
}

function createHatchPattern(id: string, color: string): SVGPatternElement {
  const pattern = document.createElementNS('http://www.w3.org/2000/svg', 'pattern')
  pattern.setAttribute('id', id)
  pattern.setAttribute('patternUnits', 'userSpaceOnUse')
  pattern.setAttribute('width', '8')
  pattern.setAttribute('height', '8')
  pattern.setAttribute('patternTransform', 'rotate(45)')

  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
  line.setAttribute('x1', '0')
  line.setAttribute('y1', '0')
  line.setAttribute('x2', '0')
  line.setAttribute('y2', '8')
  line.setAttribute('stroke', color)
  line.setAttribute('stroke-width', '3')
  line.setAttribute('stroke-opacity', '0.75')
  pattern.appendChild(line)
  return pattern
}

export function ensureAreaHatchPatternsInSvg(svg: SVGSVGElement): void {
  if (preparedSvgs.has(svg)) return

  let defs = svg.querySelector(`defs#${HATCH_DEFS_ID}`) as SVGDefsElement | null
  if (!defs) {
    defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
    defs.id = HATCH_DEFS_ID
    svg.insertBefore(defs, svg.firstChild)
  }

  if (!defs.querySelector(`#${HATCH_GREEN_ID}`)) {
    defs.appendChild(createHatchPattern(HATCH_GREEN_ID, '#2e7d32'))
  }
  if (!defs.querySelector(`#${HATCH_RED_ID}`)) {
    defs.appendChild(createHatchPattern(HATCH_RED_ID, '#c62828'))
  }

  preparedSvgs.add(svg)
}

export function createAreaSvgRenderer(map: L.Map): L.SVG {
  const renderer = L.svg({ pane: 'overlayPane' })
  renderer.addTo(map)
  const svg = (renderer as unknown as { _container: SVGSVGElement })._container
  if (svg) ensureAreaHatchPatternsInSvg(svg)
  return renderer
}

export function addAreaGeometryToGroup(
  group: L.FeatureGroup,
  geometry: GeoJSON.Geometry,
  attrs: Record<string, unknown>,
  renderer: L.SVG,
  options?: {
    interactive?: boolean
    outlineOnly?: boolean
    onEachFeature?: (layer: L.Layer) => void
  },
): void {
  const feature = {
    type: 'Feature',
    geometry,
    properties: attrs,
  } as GeoJSON.Feature

  const geoJsonOptions = {
    renderer,
    interactive: options?.interactive ?? false,
    style: () => (options?.outlineOnly ? areaOutlinePathStyle(attrs) : areaBasePathStyle(attrs)),
    onEachFeature: options?.onEachFeature
      ? (_f: GeoJSON.Feature, layer: L.Layer) => options.onEachFeature?.(layer)
      : undefined,
  } as L.GeoJSONOptions

  const baseLayer = L.geoJSON(feature, geoJsonOptions)
  baseLayer.addTo(group)

  if (!options?.outlineOnly) {
    L.geoJSON(feature, {
      renderer,
      interactive: false,
      style: () => areaHatchPathStyle(attrs),
    } as L.GeoJSONOptions).addTo(group)
  }
}
