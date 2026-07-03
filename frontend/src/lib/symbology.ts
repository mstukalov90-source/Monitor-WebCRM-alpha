import type { PathOptions } from 'leaflet'
import type { Symbology } from '../types'

/** Минимальная толщина линии на карте (удобнее кликать). */
export const MIN_LINE_WEIGHT = 5

export function lineWeight(symbology: Symbology): number {
  return Math.max(symbology.width ?? 2, MIN_LINE_WEIGHT)
}

export function pointRadius(symbology: Symbology): number {
  return symbology.size ?? 4
}

export function pointStyle(symbology: Symbology): PathOptions {
  const color = symbology.color ?? symbology.center_color ?? '#3388ff'
  return {
    color: symbology.outer_color ?? color,
    weight: symbology.outer_width ?? 1,
    fillColor: color,
    fillOpacity: symbology.opacity ?? 0.9,
  }
}

export function lineStyle(symbology: Symbology): PathOptions {
  return {
    color: symbology.color ?? '#3388ff',
    weight: lineWeight(symbology),
    opacity: symbology.opacity ?? 0.9,
  }
}

export function polygonStyle(symbology: Symbology): PathOptions {
  return {
    color: symbology.outline_color ?? symbology.fill_color ?? '#3388ff',
    weight: symbology.outline_width ?? 1,
    fillColor: symbology.fill_color ?? symbology.outline_color ?? '#3388ff',
    fillOpacity: symbology.fill_opacity ?? 0.5,
    opacity: symbology.opacity ?? 0.9,
  }
}

export function styleForGeometryType(
  geometryType: string,
  symbology: Symbology,
): PathOptions {
  if (geometryType === 'line') return lineStyle(symbology)
  if (geometryType === 'polygon') return polygonStyle(symbology)
  return pointStyle(symbology)
}
