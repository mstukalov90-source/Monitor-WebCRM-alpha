import { useCallback, useEffect, useRef, useState } from 'react'
import { AttributionControl, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchGeoJson, fetchLayersConfig } from '../api/client'
import { fetchTasksAreaGeoJson } from '../api/client'
import { findHoodLayerKey } from '../lib/hoodLayer'
import { addAreaGeometryToGroup, createAreaSvgRenderer } from '../lib/areaMapStyle'
import { pointRadius, styleForGeometryType, MIN_LINE_WEIGHT } from '../lib/symbology'
import type { TaskFeatureOnMap } from '../lib/taskFeatures'
import type { LayerConfig, LinkLayerInfo, SelectedTaskContext, TaskFeature, TaskHighlight, TaskSource } from '../types'
import { FIELD_DATA_LAYER_KEY, OFFICE_DATA_LAYER_KEY } from '../types'
import { MapResizeObserver } from './MapResizeObserver'
import {
  DISTRICT_RAYON_FIELD,
  filterDistrictGeoJson,
  MOSCOW_MAP_BBOX,
  normalizeRayonName,
  buildTaskPopupHtml,
} from '../types'

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
  taskFeatures: TaskFeatureOnMap[]
  layerConfigByKey: Map<string, LayerConfig>
  districtName?: string | null
  taskSource: TaskSource
  showTasksAreaOverlay?: boolean
  showAreaPolygons?: boolean
  showAreaPopups?: boolean
  areaOverlayOrder?: TaskFeature | null
  areaOverlayFilled?: boolean
  taskHighlight?: TaskHighlight | null
  pickMode: boolean
  pickLayers: LinkLayerInfo[]
  onFeaturePicked?: (taskColumn: string, value: string) => void
  placePointMode?: boolean
  onPointPlaced?: (lng: number, lat: number) => void
  onExecuteTask?: (ctx: SelectedTaskContext) => void | Promise<void>
  onViewArea?: (feature: TaskFeature) => void
}

const DISTRICT_BOUNDARY_STYLE: L.PathOptions = {
  color: '#cc0000',
  weight: 2,
  fillOpacity: 0,
}

function DistrictBoundaryLayer({ districtName }: { districtName?: string | null }) {
  const map = useMap()
  const layerRef = useRef<L.GeoJSON | null>(null)
  const [layerKey, setLayerKey] = useState<string | null>(null)

  useEffect(() => {
    fetchLayersConfig()
      .then((cfg) => setLayerKey(findHoodLayerKey(cfg.groups)))
      .catch(() => setLayerKey(null))
  }, [])

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (!layerKey || !districtName) return

    const districtNorm = normalizeRayonName(districtName)
    let cancelled = false

    fetchGeoJson(layerKey, MOSCOW_MAP_BBOX, 500)
      .then((geojson) => {
        if (cancelled) return

        const filtered = filterDistrictGeoJson(geojson)
        const features = filtered.features.filter(
          (feature) =>
            normalizeRayonName(String(feature.properties?.[DISTRICT_RAYON_FIELD] ?? '')) === districtNorm,
        )
        if (!features.length) return

        const gj = L.geoJSON(
          { type: 'FeatureCollection', features } as GeoJSON.FeatureCollection,
          {
            style: () => DISTRICT_BOUNDARY_STYLE,
            interactive: false,
          },
        )
        gj.addTo(map)
        layerRef.current = gj

        const bounds = gj.getBounds()
        if (bounds.isValid()) {
          map.flyToBounds(bounds, { padding: [40, 40] })
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, layerKey, districtName])

  return null
}

function SelectedAreaOrderLayer({ order, filled = false }: { order: TaskFeature; filled?: boolean }) {
  const map = useMap()
  const layerRef = useRef<L.FeatureGroup | null>(null)
  const rendererRef = useRef<L.SVG | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (rendererRef.current) {
      map.removeLayer(rendererRef.current)
      rendererRef.current = null
    }
    if (!order.geometry) return

    const renderer = createAreaSvgRenderer(map)
    rendererRef.current = renderer
    const group = L.featureGroup()
    addAreaGeometryToGroup(group, order.geometry, order.attributes, renderer, {
      interactive: false,
      outlineOnly: !filled,
    })
    group.addTo(map)
    layerRef.current = group

    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.flyToBounds(bounds, { padding: [40, 40] })
    }

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
      if (rendererRef.current) {
        map.removeLayer(rendererRef.current)
        rendererRef.current = null
      }
    }
  }, [map, order, filled])

  return null
}

function TasksAreaLayer({ districtName }: { districtName?: string | null }) {
  const map = useMap()
  const layerRef = useRef<L.FeatureGroup | null>(null)
  const rendererRef = useRef<L.SVG | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (rendererRef.current) {
      map.removeLayer(rendererRef.current)
      rendererRef.current = null
    }
    if (!districtName) return

    let cancelled = false
    const renderer = createAreaSvgRenderer(map)
    rendererRef.current = renderer

    fetchTasksAreaGeoJson(districtName)
      .then((geojson) => {
        if (cancelled) return
        const group = L.featureGroup()
        for (const item of geojson.features ?? []) {
          const geometry = item.geometry
          if (!geometry) continue
          const attrs = { ...(item.properties ?? {}) }
          addAreaGeometryToGroup(group, geometry, attrs, renderer, { interactive: false })
        }
        group.addTo(map)
        layerRef.current = group
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
      if (rendererRef.current) {
        map.removeLayer(rendererRef.current)
        rendererRef.current = null
      }
    }
  }, [map, districtName])

  return null
}

function bindMapPopup(
  layer: L.Layer,
  popupHtml: string,
  ctx: SelectedTaskContext,
  options?: {
    onExecuteTask?: (ctx: SelectedTaskContext) => void | Promise<void>
    onViewArea?: (feature: TaskFeature) => void
  },
) {
  layer.bindPopup(popupHtml)

  layer.on('popupopen', () => {
    const popupEl = layer.getPopup()?.getElement()
    if (!popupEl) return

    const executeBtn = popupEl.querySelector<HTMLButtonElement>('[data-map-action="execute-task"]')
    if (executeBtn && options?.onExecuteTask) {
      const handleExecute = (event: Event) => {
        L.DomEvent.stopPropagation(event)
        L.DomEvent.preventDefault(event)
        executeBtn.disabled = true
        void Promise.resolve(options.onExecuteTask!(ctx))
          .then(() => layer.closePopup())
          .catch(() => {
            executeBtn.disabled = false
          })
      }
      executeBtn.addEventListener('click', handleExecute, { once: true })
    }

    const viewAreaBtn = popupEl.querySelector<HTMLButtonElement>('[data-map-action="view-area-order"]')
    if (viewAreaBtn && options?.onViewArea) {
      const handleViewArea = (event: Event) => {
        L.DomEvent.stopPropagation(event)
        L.DomEvent.preventDefault(event)
        options.onViewArea!(ctx.feature)
        layer.closePopup()
      }
      viewAreaBtn.addEventListener('click', handleViewArea, { once: true })
    }
  })
}

function bindTaskPopup(
  layer: L.Layer,
  taskFeat: TaskFeatureOnMap,
  taskSource: TaskSource,
  options?: {
    onExecuteTask?: (ctx: SelectedTaskContext) => void | Promise<void>
    onViewArea?: (feature: TaskFeature) => void
  },
) {
  const popupHtml = buildTaskPopupHtml(taskFeat, taskFeat.subgroupName, taskSource)
  bindMapPopup(
    layer,
    popupHtml,
    {
      groupName: taskFeat.groupName,
      subgroupName: taskFeat.subgroupName,
      feature: taskFeat,
      taskKey: taskFeat.task_key ?? undefined,
      taskSource,
    },
    options,
  )
}

function TaskFeaturesLayer({
  taskFeatures,
  layerConfigByKey,
  taskSource,
  showAreaPopups,
  showAreaPolygons = true,
  onExecuteTask,
  onViewArea,
}: {
  taskFeatures: TaskFeatureOnMap[]
  layerConfigByKey: Map<string, LayerConfig>
  taskSource: TaskSource
  showAreaPopups: boolean
  showAreaPolygons?: boolean
  onExecuteTask?: (ctx: SelectedTaskContext) => void | Promise<void>
  onViewArea?: (feature: TaskFeature) => void
}) {
  const map = useMap()
  const groupRef = useRef<L.FeatureGroup | null>(null)
  const rendererRef = useRef<L.SVG | null>(null)

  useEffect(() => {
    if (groupRef.current) {
      map.removeLayer(groupRef.current)
      groupRef.current = null
    }
    if (rendererRef.current) {
      map.removeLayer(rendererRef.current)
      rendererRef.current = null
    }

    const withGeom = taskFeatures.filter((f) => f.geometry)
    if (!withGeom.length) return

    const areaFeatures = showAreaPolygons
      ? withGeom.filter((f) => f.layer_key === 'tasks_area')
      : []
    const otherFeatures = withGeom.filter((f) => f.layer_key !== 'tasks_area')
    const sortedFeatures = [...areaFeatures, ...otherFeatures]

    if (!sortedFeatures.length) return

    const group = L.featureGroup()
    let areaRenderer: L.SVG | null = null
    if (areaFeatures.length) {
      areaRenderer = createAreaSvgRenderer(map)
      rendererRef.current = areaRenderer
    }

    sortedFeatures.forEach((taskFeat) => {
      const layerCfg = layerConfigByKey.get(taskFeat.layer_key)
      const isAreaLayer = taskFeat.layer_key === 'tasks_area'
      const isFieldDataLayer = taskFeat.layer_key === FIELD_DATA_LAYER_KEY
      const isOfficeDataLayer = taskFeat.layer_key === OFFICE_DATA_LAYER_KEY
      const geomType = layerCfg?.geometry_type ?? (isAreaLayer ? 'polygon' : 'point')
      const symbology =
        layerCfg?.symbology ??
        (isFieldDataLayer
          ? { color: '#7B1FA2', size: 7, marker_type: 'circle' }
          : isOfficeDataLayer
            ? { color: '#E65100', size: 7, marker_type: 'circle' }
            : {})
      const areaInteractive = isAreaLayer && showAreaPopups

      if (isAreaLayer && areaRenderer && taskFeat.geometry) {
        addAreaGeometryToGroup(
          group,
          taskFeat.geometry as GeoJSON.Geometry,
          taskFeat.attributes,
          areaRenderer,
          {
            interactive: areaInteractive,
            onEachFeature: (layer) => {
              if (!showAreaPopups) return
              bindTaskPopup(layer, taskFeat, taskSource, { onExecuteTask, onViewArea })
            },
          },
        )
        return
      }

      const gj = L.geoJSON(
        {
          type: 'Feature',
          geometry: taskFeat.geometry as GeoJSON.Geometry,
          properties: taskFeat.attributes,
        } as GeoJSON.Feature,
        {
          interactive: !isAreaLayer || areaInteractive,
          pointToLayer: (_feature, latlng) =>
            L.circleMarker(latlng, {
              radius: pointRadius(symbology),
              ...styleForGeometryType(geomType, symbology),
            }),
          style: () => styleForGeometryType(geomType, symbology),
          onEachFeature: (_feature, layer) => {
            if (isAreaLayer && !showAreaPopups) return
            bindTaskPopup(layer, taskFeat, taskSource, { onExecuteTask, onViewArea })
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
      if (rendererRef.current) map.removeLayer(rendererRef.current)
    }
  }, [map, taskFeatures, layerConfigByKey, taskSource, showAreaPopups, showAreaPolygons, onExecuteTask, onViewArea])

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
            style: (feature) => {
              const isLine =
                feature?.geometry?.type === 'LineString' ||
                feature?.geometry?.type === 'MultiLineString'
              return {
                color: '#0066cc',
                weight: isLine ? MIN_LINE_WEIGHT : 3,
                fillOpacity: 0.2,
              }
            },
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

function PlacePointHandler({
  active,
  onPointPlaced,
}: {
  active: boolean
  onPointPlaced?: (lng: number, lat: number) => void
}) {
  useMapEvents({
    click(e) {
      if (!active || !onPointPlaced) return
      onPointPlaced(e.latlng.lng, e.latlng.lat)
    },
  })
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
    weight: isLine ? Math.max(palette.weight, MIN_LINE_WEIGHT) : palette.weight,
    dashArray: isLine && palette === HIGHLIGHT_LINKED ? HIGHLIGHT_LINKED.dashArray : undefined,
    fillColor: palette.color,
    fillOpacity: isPolygon ? palette.fillOpacity : 0,
  }
}

function addHighlightFeature(
  group: L.FeatureGroup,
  geometry: GeoJSON.Geometry,
  palette: typeof HIGHLIGHT_PRIMARY | typeof HIGHLIGHT_LINKED,
  options?: {
    popupHtml?: string
    popupCtx?: SelectedTaskContext
    onExecuteTask?: (ctx: SelectedTaskContext) => void | Promise<void>
    onViewArea?: (feature: TaskFeature) => void
  },
): L.GeoJSON | null {
  let primaryLayer: L.GeoJSON | null = null
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
      onEachFeature: options?.popupHtml
        ? (_feature, pathLayer) => {
            if (options.popupCtx) {
              bindMapPopup(pathLayer, options.popupHtml!, options.popupCtx, {
                onExecuteTask: options.onExecuteTask,
                onViewArea: options.onViewArea,
              })
            } else {
              pathLayer.bindPopup(options.popupHtml!)
            }
          }
        : undefined,
    },
  )
  layer.addTo(group)
  if (palette === HIGHLIGHT_PRIMARY) primaryLayer = layer
  return primaryLayer
}

function TaskHighlightLayer({
  highlight,
  taskSource,
  onExecuteTask,
  onViewArea,
}: {
  highlight?: TaskHighlight | null
  taskSource: TaskSource
  onExecuteTask?: (ctx: SelectedTaskContext) => void | Promise<void>
  onViewArea?: (feature: TaskFeature) => void
}) {
  const map = useMap()
  const groupRef = useRef<L.FeatureGroup | null>(null)

  useEffect(() => {
    if (groupRef.current) {
      map.removeLayer(groupRef.current)
      groupRef.current = null
    }
    if (!highlight?.primary && !highlight?.linked.length) return

    const group = L.featureGroup()
    let primaryLayer: L.GeoJSON | null = null

    if (highlight.primary) {
      const popup = highlight.popup
      const popupHtml = popup
        ? buildTaskPopupHtml(popup.feature, popup.subgroupName, taskSource)
        : undefined
      const popupCtx: SelectedTaskContext | undefined = popup
        ? {
            groupName: popup.groupName,
            subgroupName: popup.subgroupName,
            feature: popup.feature,
            taskKey: popup.taskKey,
            taskSource,
          }
        : undefined
      primaryLayer = addHighlightFeature(group, highlight.primary, HIGHLIGHT_PRIMARY, {
        popupHtml,
        popupCtx,
        onExecuteTask,
        onViewArea,
      })
    }

    highlight.linked.forEach((linked) => {
      if (!linked.geometry) return
      addHighlightFeature(
        group,
        linked.geometry,
        HIGHLIGHT_LINKED,
        {
          popupHtml: `<b>Привязка: ${linked.link_column}</b><br/>${linked.layer_name}`,
        },
      )
    })

    group.addTo(map)
    groupRef.current = group

    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.flyToBounds(bounds, { padding: [40, 40] })
    }

    if (primaryLayer && highlight.popup) {
      primaryLayer.eachLayer((layer) => {
        layer.openPopup()
      })
    }

    return () => {
      if (groupRef.current) map.removeLayer(groupRef.current)
    }
  }, [highlight, map, taskSource, onExecuteTask, onViewArea])

  return null
}

export function MapView({
  taskFeatures,
  layerConfigByKey,
  districtName,
  taskSource,
  showTasksAreaOverlay = true,
  showAreaPolygons = true,
  showAreaPopups = false,
  areaOverlayOrder = null,
  areaOverlayFilled = false,
  taskHighlight,
  pickMode,
  pickLayers,
  onFeaturePicked,
  placePointMode = false,
  onPointPlaced,
  onExecuteTask,
  onViewArea,
}: MapViewProps) {
  return (
    <MapContainer
      center={MOSCOW_CENTER}
      zoom={11}
      maxZoom={MAP_MAX_ZOOM}
      attributionControl={false}
      className={`map-container${placePointMode ? ' map-container--place-point' : ''}`}
      style={{ height: '100%', width: '100%' }}
    >
      <MapResizeObserver />
      <AttributionControl prefix={LEAFLET_ATTRIBUTION_PREFIX} />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={MAP_MAX_ZOOM}
      />
      <DistrictBoundaryLayer districtName={districtName} />
      {!pickMode && (
        <>
          {areaOverlayOrder && (
            <SelectedAreaOrderLayer order={areaOverlayOrder} filled={areaOverlayFilled} />
          )}
          {showTasksAreaOverlay && !areaOverlayOrder && (
            <TasksAreaLayer districtName={districtName} />
          )}
          <TaskFeaturesLayer
            taskFeatures={taskFeatures}
            layerConfigByKey={layerConfigByKey}
            taskSource={taskSource}
            showAreaPopups={showAreaPopups}
            showAreaPolygons={showAreaPolygons}
            onExecuteTask={onExecuteTask}
            onViewArea={onViewArea}
          />
        </>
      )}
      <PickLayerLoader
        pickMode={pickMode}
        pickLayers={pickLayers}
        onFeaturePicked={onFeaturePicked}
      />
      <PlacePointHandler active={placePointMode && !pickMode} onPointPlaced={onPointPlaced} />
      <TaskHighlightLayer
        highlight={taskHighlight}
        taskSource={taskSource}
        onExecuteTask={onExecuteTask}
        onViewArea={onViewArea}
      />
    </MapContainer>
  )
}

export function geometryFromTaskFeature(feature: TaskFeature): GeoJSON.Geometry | null {
  return feature.geometry ?? null
}
