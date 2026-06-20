import { useCallback, useEffect, useRef } from 'react'
import { AttributionControl, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchGeoJson } from '../api/client'
import { fetchTasksAreaGeoJson } from '../api/client'
import { pointRadius, styleForGeometryType } from '../lib/symbology'
import type { LayerConfig, LinkLayerInfo, TaskFeature, TaskHighlight } from '../types'

const MOSCOW_CENTER: [number, number] = [55.7558, 37.6173]
const MAP_MAX_ZOOM = 19

const RUSSIAN_FLAG_SVG =
  '<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="12" height="8" viewBox="0 0 12 8" class="leaflet-attribution-flag">' +
  '<path fill="#fff" d="M0 0h12v2.67H0z"/>' +
  '<path fill="#0039A6" d="M0 2.67h12v2.66H0z"/>' +
  '<path fill="#D52B1E" d="M0 5.33h12v2.67H0z"/>' +
  '</svg>'

const LEAFLET_ATTRIBUTION_PREFIX =
  `<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">${RUSSIAN_FLAG_SVG} Leaflet</a>`

interface MapViewProps {
  taskFeatures: TaskFeature[]
  layerConfigByKey: Map<string, LayerConfig>
  districtName?: string | null
  showTasksAreaOverlay?: boolean
  taskHighlight?: TaskHighlight | null
  pickMode: boolean
  pickLayers: LinkLayerInfo[]
  onFeaturePicked?: (taskColumn: string, value: string) => void
}

const TASKS_AREA_STYLE: L.PathOptions = {
  color: '#0066cc',
  weight: 2,
  fillOpacity: 0,
}

function TasksAreaLayer({ districtName }: { districtName?: string | null }) {
  const map = useMap()
  const layerRef = useRef<L.GeoJSON | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (!districtName) return

    let cancelled = false
    fetchTasksAreaGeoJson(districtName)
      .then((geojson) => {
        if (cancelled) return
        const gj = L.geoJSON(geojson, {
          style: () => TASKS_AREA_STYLE,
          onEachFeature: (feature, layer) => {
            const props = feature.properties || {}
            const lines = [
              '<b>Площадные заказы</b>',
              ...Object.entries(props)
                .filter(([k]) => k !== 'geom')
                .slice(0, 8)
                .map(([k, v]) => `<b>${k}</b>: ${v}`),
            ].join('<br/>')
            layer.bindPopup(`<div style="max-height:200px;overflow:auto">${lines}</div>`)
          },
        })
        gj.addTo(map)
        layerRef.current = gj
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, districtName])

  return null
}

function TaskFeaturesLayer({
  taskFeatures,
  layerConfigByKey,
}: {
  taskFeatures: TaskFeature[]
  layerConfigByKey: Map<string, LayerConfig>
}) {
  const map = useMap()
  const groupRef = useRef<L.FeatureGroup | null>(null)

  useEffect(() => {
    if (groupRef.current) {
      map.removeLayer(groupRef.current)
      groupRef.current = null
    }

    const withGeom = taskFeatures.filter((f) => f.geometry)
    if (!withGeom.length) return

    const group = L.featureGroup()
    withGeom.forEach((taskFeat) => {
      const layerCfg = layerConfigByKey.get(taskFeat.layer_key)
      const isAreaLayer = taskFeat.layer_key === 'tasks_area'
      const geomType = layerCfg?.geometry_type ?? (isAreaLayer ? 'polygon' : 'point')
      const symbology = layerCfg?.symbology ?? {}

      const gj = L.geoJSON(
        {
          type: 'Feature',
          geometry: taskFeat.geometry as GeoJSON.Geometry,
          properties: taskFeat.attributes,
        } as GeoJSON.Feature,
        {
          pointToLayer: (_feature, latlng) =>
            L.circleMarker(latlng, {
              radius: pointRadius(symbology),
              ...styleForGeometryType(geomType, symbology),
            }),
          style: () =>
            isAreaLayer
              ? TASKS_AREA_STYLE
              : styleForGeometryType(geomType, symbology),
          onEachFeature: (feature, layer) => {
            const props = feature.properties || {}
            const lines = [
              `<b>${taskFeat.layer_name}</b>`,
              ...Object.entries(props)
                .slice(0, 10)
                .map(([k, v]) => `<b>${k}</b>: ${v}`),
            ].join('<br/>')
            layer.bindPopup(`<div style="max-height:200px;overflow:auto">${lines}</div>`)
          },
        },
      )
      gj.addTo(group)
    })

    group.addTo(map)
    groupRef.current = group

    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }

    return () => {
      if (groupRef.current) map.removeLayer(groupRef.current)
    }
  }, [map, taskFeatures, layerConfigByKey])

  return null
}

function PickLayerLoader({
  pickMode,
  pickLayers,
  onFeaturePicked,
}: {
  pickMode: boolean
  pickLayers: LinkLayerInfo[]
  onFeaturePicked?: (taskColumn: string, value: string) => void
}) {
  const map = useMap()
  const pickGroupsRef = useRef<Map<string, L.GeoJSON>>(new Map())
  const debounceRef = useRef<number | null>(null)

  const loadPickLayers = useCallback(() => {
    if (!pickMode) {
      pickGroupsRef.current.forEach((layer) => map.removeLayer(layer))
      pickGroupsRef.current.clear()
      return
    }

    const bounds = map.getBounds()
    const bbox = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ].join(',')

    pickGroupsRef.current.forEach((layer) => map.removeLayer(layer))
    pickGroupsRef.current.clear()

    const uniqueKeys = [...new Set(pickLayers.map((l) => l.layer_key))]
    uniqueKeys.forEach((layerKey) => {
      const info = pickLayers.find((l) => l.layer_key === layerKey)
      if (!info) return

      fetchGeoJson(layerKey, bbox)
        .then((geojson) => {
          const gj = L.geoJSON(geojson, {
            pointToLayer: (_feature, latlng) =>
              L.circleMarker(latlng, {
                radius: 8,
                color: '#0066cc',
                weight: 2,
                fillColor: '#66aaff',
                fillOpacity: 0.8,
              }),
            style: { color: '#0066cc', weight: 3, fillOpacity: 0.2 },
            onEachFeature: (feature, layer) => {
              layer.on('click', (e) => {
                L.DomEvent.stopPropagation(e)
                const props = feature.properties || {}
                const value = props[info.source_field]
                if (value != null && value !== '' && onFeaturePicked) {
                  onFeaturePicked(info.task_column, String(value))
                }
              })
            },
          })
          gj.addTo(map)
          pickGroupsRef.current.set(layerKey, gj)
        })
        .catch(() => {})
    })
  }, [map, pickMode, pickLayers, onFeaturePicked])

  useMapEvents({
    moveend: () => {
      if (!pickMode) return
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
      debounceRef.current = window.setTimeout(loadPickLayers, 300)
    },
    zoomend: () => {
      if (!pickMode) return
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
      debounceRef.current = window.setTimeout(loadPickLayers, 300)
    },
  })

  useEffect(() => {
    loadPickLayers()
  }, [loadPickLayers])

  return null
}

const HIGHLIGHT_PRIMARY = { color: '#ff6600', weight: 4, fillOpacity: 0.15 }
const HIGHLIGHT_LINKED = {
  color: '#0066cc',
  weight: 3,
  dashArray: '8 6' as const,
  fillOpacity: 0.12,
}

function isPointGeometry(geometry: GeoJSON.Geometry): boolean {
  return geometry.type === 'Point' || geometry.type === 'MultiPoint'
}

function highlightPathStyle(
  geometry: GeoJSON.Geometry,
  palette: typeof HIGHLIGHT_PRIMARY | typeof HIGHLIGHT_LINKED,
): L.PathOptions {
  const isPolygon = geometry.type === 'Polygon' || geometry.type === 'MultiPolygon'
  const isLine =
    geometry.type === 'LineString' || geometry.type === 'MultiLineString'
  return {
    color: palette.color,
    weight: palette.weight,
    dashArray: isLine && palette === HIGHLIGHT_LINKED ? HIGHLIGHT_LINKED.dashArray : undefined,
    fillColor: palette.color,
    fillOpacity: isPolygon ? palette.fillOpacity : 0,
  }
}

function addHighlightFeature(
  group: L.FeatureGroup,
  geometry: GeoJSON.Geometry,
  palette: typeof HIGHLIGHT_PRIMARY | typeof HIGHLIGHT_LINKED,
  popupHtml?: string,
) {
  const layer = L.geoJSON(
    { type: 'Feature', geometry, properties: {} } as GeoJSON.Feature,
    {
      pointToLayer: (_f, latlng) =>
        L.circleMarker(latlng, {
          radius: palette === HIGHLIGHT_PRIMARY ? 12 : 10,
          color: palette.color,
          weight: palette === HIGHLIGHT_PRIMARY ? 3 : 2,
          dashArray: palette === HIGHLIGHT_LINKED ? '4 4' : undefined,
          fillOpacity: palette === HIGHLIGHT_PRIMARY ? 0.3 : 0.25,
        }),
      style: (feature) => {
        if (!feature?.geometry || isPointGeometry(feature.geometry)) {
          return {}
        }
        return highlightPathStyle(feature.geometry, palette)
      },
      onEachFeature: popupHtml
        ? (_feature, pathLayer) => {
            pathLayer.bindPopup(popupHtml)
          }
        : undefined,
    },
  )
  layer.addTo(group)
}

function TaskHighlightLayer({ highlight }: { highlight?: TaskHighlight | null }) {
  const map = useMap()
  const groupRef = useRef<L.FeatureGroup | null>(null)

  useEffect(() => {
    if (groupRef.current) {
      map.removeLayer(groupRef.current)
      groupRef.current = null
    }
    if (!highlight?.primary && !highlight?.linked.length) return

    const group = L.featureGroup()

    if (highlight.primary) {
      addHighlightFeature(group, highlight.primary, HIGHLIGHT_PRIMARY)
    }

    highlight.linked.forEach((linked) => {
      if (!linked.geometry) return
      addHighlightFeature(
        group,
        linked.geometry,
        HIGHLIGHT_LINKED,
        `<b>Привязка: ${linked.link_column}</b><br/>${linked.layer_name}`,
      )
    })

    group.addTo(map)
    groupRef.current = group

    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.flyToBounds(bounds, { padding: [40, 40] })
    }

    return () => {
      if (groupRef.current) map.removeLayer(groupRef.current)
    }
  }, [highlight, map])

  return null
}

export function MapView({
  taskFeatures,
  layerConfigByKey,
  districtName,
  showTasksAreaOverlay = true,
  taskHighlight,
  pickMode,
  pickLayers,
  onFeaturePicked,
}: MapViewProps) {
  return (
    <MapContainer
      center={MOSCOW_CENTER}
      zoom={11}
      maxZoom={MAP_MAX_ZOOM}
      attributionControl={false}
      className="map-container"
      style={{ height: '100%', width: '100%' }}
    >
      <AttributionControl prefix={LEAFLET_ATTRIBUTION_PREFIX} />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={MAP_MAX_ZOOM}
      />
      {!pickMode && (
        <>
          {showTasksAreaOverlay && <TasksAreaLayer districtName={districtName} />}
          <TaskFeaturesLayer taskFeatures={taskFeatures} layerConfigByKey={layerConfigByKey} />
        </>
      )}
      <PickLayerLoader
        pickMode={pickMode}
        pickLayers={pickLayers}
        onFeaturePicked={onFeaturePicked}
      />
      <TaskHighlightLayer highlight={taskHighlight} />
    </MapContainer>
  )
}

export function geometryFromTaskFeature(feature: TaskFeature): GeoJSON.Geometry | null {
  return feature.geometry ?? null
}
