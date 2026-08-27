import { useMemo } from 'react'
import type { TaskFeatureOnMap } from '../lib/taskFeatures'
import { buildMapLegendItems, swatchStyles, type MapLegendItem } from '../lib/mapLegend'
import type { LayerConfig, NearbyContextKind } from '../types'

interface MapLegendProps {
  taskFeatures: TaskFeatureOnMap[]
  layerConfigByKey: Map<string, LayerConfig>
  showAreaOverlay: boolean
  isAreaMode?: boolean
  showDistrictBoundary?: boolean
  showFieldReports?: boolean
  nearbyOverlayKinds?: NearbyContextKind[]
}

function LegendSwatch({ item }: { item: MapLegendItem }) {
  const styles = swatchStyles(item)

  if (item.kind === 'area-hatch') {
    return <span className="legend-swatch legend-swatch-polygon" style={styles.polygon} />
  }
  if (item.kind === 'line') {
    return <span className="legend-swatch legend-swatch-line" style={styles.line} />
  }
  if (item.kind === 'polygon') {
    return <span className="legend-swatch legend-swatch-polygon" style={styles.polygon} />
  }
  if (item.kind === 'highlight-linked') {
    return <span className="legend-swatch legend-swatch-line" style={styles.line} />
  }
  if (item.kind === 'highlight-report') {
    return (
      <img
        className="legend-swatch legend-swatch-report"
        src="/report.png"
        alt=""
        aria-hidden="true"
      />
    )
  }
  if (item.kind === 'highlight-primary') {
    return <span className="legend-swatch legend-swatch-polygon" style={styles.polygon} />
  }

  return <span className="legend-swatch legend-swatch-point" style={styles.point} />
}

export function MapLegend({
  taskFeatures,
  layerConfigByKey,
  showAreaOverlay,
  isAreaMode = false,
  showDistrictBoundary = true,
  showFieldReports = false,
  nearbyOverlayKinds = [],
}: MapLegendProps) {
  const items = useMemo(
    () =>
      buildMapLegendItems(taskFeatures, layerConfigByKey, {
        showAreaOverlay,
        isAreaMode,
        showDistrictBoundary,
        showFieldReports,
        nearbyOverlayKinds,
      }),
    [taskFeatures, layerConfigByKey, showAreaOverlay, isAreaMode, showDistrictBoundary, showFieldReports, nearbyOverlayKinds],
  )

  if (!items.length) return null

  return (
    <div className="map-legend">
      <h4 className="map-legend-title">Условные обозначения</h4>
      <ul className="map-legend-list">
        {items.map((item) => (
          <li key={item.id} className="map-legend-item">
            <LegendSwatch item={item} />
            <span className="map-legend-label">{item.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
