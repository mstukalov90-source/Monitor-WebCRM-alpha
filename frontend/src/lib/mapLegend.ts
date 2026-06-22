import type { CSSProperties } from 'react'
import { lineStyle, pointStyle, polygonStyle } from './symbology'
import type { TaskFeatureOnMap } from './taskFeatures'
import type { LayerConfig, Symbology } from '../types'

export type LegendSwatchKind = 'point' | 'line' | 'polygon' | 'highlight-primary' | 'highlight-linked'

export interface MapLegendItem {
  id: string
  label: string
  kind: LegendSwatchKind
  symbology?: Symbology
}

const AREA_OVERLAY_ITEM: MapLegendItem = {
  id: 'tasks_area_overlay',
  label: 'Площадные заказы',
  kind: 'polygon',
  symbology: {
    color: '#0066cc',
    fill_color: '#0066cc',
    fill_opacity: 0,
    outline_width: 2,
  },
}

const DISTRICT_BOUNDARY_ITEM: MapLegendItem = {
  id: 'district_boundary',
  label: 'Граница района',
  kind: 'polygon',
  symbology: {
    color: '#cc0000',
    fill_color: '#ff6666',
    fill_opacity: 0.06,
    outline_width: 2,
  },
}

const HIGHLIGHT_PRIMARY_ITEM: MapLegendItem = {
  id: 'highlight_primary',
  label: 'Выбранная задача',
  kind: 'highlight-primary',
}

const HIGHLIGHT_LINKED_ITEM: MapLegendItem = {
  id: 'highlight_linked',
  label: 'Привязанные объекты',
  kind: 'highlight-linked',
}

export function buildMapLegendItems(
  taskFeatures: TaskFeatureOnMap[],
  layerConfigByKey: Map<string, LayerConfig>,
  options: { showAreaOverlay: boolean; showDistrictBoundary?: boolean },
): MapLegendItem[] {
  const items: MapLegendItem[] = []
  const seen = new Set<string>()

  if (options.showDistrictBoundary) {
    items.push(DISTRICT_BOUNDARY_ITEM)
  }

  for (const feat of taskFeatures) {
    if (!feat.geometry) continue
    if (seen.has(feat.layer_key)) continue
    seen.add(feat.layer_key)

    const cfg = layerConfigByKey.get(feat.layer_key)
    if (feat.layer_key === 'tasks_area') {
      items.push({
        id: 'tasks_area',
        label: feat.layer_name || 'Площадные заказы',
        kind: 'polygon',
        symbology: AREA_OVERLAY_ITEM.symbology,
      })
      continue
    }

    const geometryType = cfg?.geometry_type ?? 'point'
    items.push({
      id: feat.layer_key,
      label: cfg?.display_name ?? feat.layer_name,
      kind: geometryType === 'line' ? 'line' : geometryType === 'polygon' ? 'polygon' : 'point',
      symbology: cfg?.symbology ?? {},
    })
  }

  items.sort((a, b) => a.label.localeCompare(b.label, 'ru'))

  if (options.showAreaOverlay && !seen.has('tasks_area')) {
    items.push(AREA_OVERLAY_ITEM)
    items.sort((a, b) => a.label.localeCompare(b.label, 'ru'))
  }

  items.push(HIGHLIGHT_PRIMARY_ITEM, HIGHLIGHT_LINKED_ITEM)
  return items
}

export function swatchStyles(item: MapLegendItem): {
  point?: CSSProperties
  line?: CSSProperties
  polygon?: CSSProperties
} {
  if (item.kind === 'highlight-primary') {
    return {
      point: {
        backgroundColor: 'rgba(255, 102, 0, 0.3)',
        borderColor: '#ff6600',
        borderWidth: 2,
      },
      line: { backgroundColor: '#ff6600', height: 3 },
      polygon: {
        backgroundColor: 'rgba(255, 102, 0, 0.15)',
        borderColor: '#ff6600',
        borderWidth: 2,
      },
    }
  }

  if (item.kind === 'highlight-linked') {
    return {
      point: {
        backgroundColor: 'rgba(0, 102, 204, 0.25)',
        borderColor: '#0066cc',
        borderWidth: 2,
        borderStyle: 'dashed',
      },
      line: {
        backgroundColor: 'transparent',
        borderTop: '3px dashed #0066cc',
        height: 0,
      },
      polygon: {
        backgroundColor: 'rgba(0, 102, 204, 0.12)',
        borderColor: '#0066cc',
        borderWidth: 2,
        borderStyle: 'dashed',
      },
    }
  }

  const symbology = item.symbology ?? {}
  if (item.kind === 'line') {
    const s = lineStyle(symbology)
    return { line: { backgroundColor: String(s.color ?? '#3388ff'), height: Math.max(2, Number(s.weight) || 2) } }
  }
  if (item.kind === 'polygon') {
    const s = polygonStyle(symbology)
    const fillOpacity = s.fillOpacity ?? 0.5
    return {
      polygon: {
        backgroundColor:
          fillOpacity === 0 ? 'transparent' : String(s.fillColor ?? '#3388ff'),
        borderColor: String(s.color ?? '#3388ff'),
        borderWidth: Number(s.weight) || 1,
      },
    }
  }

  const s = pointStyle(symbology)
  return {
    point: {
      backgroundColor: String(s.fillColor ?? '#3388ff'),
      borderColor: String(s.color ?? '#3388ff'),
      borderWidth: Number(s.weight) || 1,
    },
  }
}
