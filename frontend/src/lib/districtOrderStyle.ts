import type { PathOptions } from 'leaflet'
import type { TaskFeature } from '../types'
import { AREA_STATUS_COLORS, areaStatusFromAttributes, isAnaliseComplete } from '../types'

export type DistrictFillKind = 'done' | 'free' | 'empty' | 'mixed'
export type DistrictHatchKind = 'green' | 'red' | 'none'

export interface DistrictOrderVisual {
  fill: DistrictFillKind
  hatch: DistrictHatchKind
}

/** Fill colors for district polygons aggregated from area orders. */
export const DISTRICT_FILL_COLORS: Record<
  DistrictFillKind,
  { color: string; fillColor: string; fillOpacity: number }
> = {
  done: {
    color: AREA_STATUS_COLORS.done,
    fillColor: AREA_STATUS_COLORS.done,
    fillOpacity: 0.35,
  },
  /** Same red as previous HOOD_STYLE_DEFAULT when any order is free. */
  free: {
    color: '#cc0000',
    fillColor: '#ff6666',
    fillOpacity: 0.35,
  },
  empty: {
    color: '#212121',
    fillColor: '#212121',
    fillOpacity: 0.35,
  },
  mixed: {
    color: AREA_STATUS_COLORS.wip,
    fillColor: AREA_STATUS_COLORS.wip,
    fillOpacity: 0.35,
  },
}

export function districtOrderVisual(orders: TaskFeature[]): DistrictOrderVisual {
  if (!orders.length) {
    return { fill: 'empty', hatch: 'none' }
  }

  const statuses = orders.map((o) => areaStatusFromAttributes(o.attributes))
  const hasFree = statuses.some((s) => s === 'free')
  const allDone = statuses.every((s) => s === 'done')

  let fill: DistrictFillKind
  if (allDone) fill = 'done'
  else if (hasFree) fill = 'free'
  else fill = 'mixed'

  const allAnalysed = orders.every((o) => isAnaliseComplete(o.attributes.analise))
  const hatch: DistrictHatchKind = allAnalysed ? 'green' : 'red'

  return { fill, hatch }
}

export function districtBasePathStyle(
  visual: DistrictOrderVisual,
  selected: boolean,
): PathOptions {
  const colors = DISTRICT_FILL_COLORS[visual.fill]
  return {
    color: selected ? '#0d6efd' : colors.color,
    weight: selected ? 3 : 2,
    fillColor: colors.fillColor,
    fillOpacity: colors.fillOpacity,
  }
}

export function buildDistrictStyleByRayon(
  groups: { rayon: string; orders: TaskFeature[] }[],
): Map<string, DistrictOrderVisual> {
  const map = new Map<string, DistrictOrderVisual>()
  for (const group of groups) {
    map.set(group.rayon, districtOrderVisual(group.orders))
  }
  return map
}
