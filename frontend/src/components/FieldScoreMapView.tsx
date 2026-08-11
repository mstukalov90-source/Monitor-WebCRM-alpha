import { useEffect, useRef } from 'react'
import { AttributionControl, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { BasemapLayers } from './BasemapLayers'
import { MapResizeObserver } from './MapResizeObserver'
import type { FieldScoreTask, FieldScoreTrack } from '../types'

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

const ORDER_STYLE: L.PathOptions = {
  color: '#212121',
  weight: 2,
  fillColor: '#ff9800',
  fillOpacity: 0.18,
}

const TRACK_STYLE: L.PathOptions = {
  color: '#0d6efd',
  weight: 3,
  opacity: 0.9,
}

const BUFFER_STYLE: L.PathOptions = {
  color: '#0d6efd',
  weight: 1,
  fillColor: '#0d6efd',
  fillOpacity: 0.12,
  opacity: 0.45,
}

const TASK_PATH_STYLE: L.PathOptions = {
  color: '#2e7d32',
  weight: 2,
  fillColor: '#66bb6a',
  fillOpacity: 0.55,
}

const TASK_POINT_RADIUS = 6

interface FieldScoreMapViewProps {
  orderGeometry: GeoJSON.Geometry | null | undefined
  tasks: FieldScoreTask[]
  tracks: FieldScoreTrack[]
  selectedTaskKey: string | null
  onSelectTask?: (taskKey: string) => void
}

function FitLayers({
  orderGeometry,
  tasks,
  tracks,
}: {
  orderGeometry: GeoJSON.Geometry | null | undefined
  tasks: FieldScoreTask[]
  tracks: FieldScoreTrack[]
}) {
  const map = useMap()

  useEffect(() => {
    const layers: L.Layer[] = []
    if (orderGeometry) {
      layers.push(L.geoJSON(orderGeometry as GeoJSON.GeoJsonObject))
    }
    for (const track of tracks) {
      if (track.geometry) layers.push(L.geoJSON(track.geometry as GeoJSON.GeoJsonObject))
    }
    for (const task of tasks) {
      if (task.geometry) layers.push(L.geoJSON(task.geometry as GeoJSON.GeoJsonObject))
    }
    if (!layers.length) return
    const group = L.featureGroup(layers)
    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }
  }, [map, orderGeometry, tasks, tracks])

  return null
}

function ScoreLayers({
  orderGeometry,
  tasks,
  tracks,
  selectedTaskKey,
  onSelectTask,
}: FieldScoreMapViewProps) {
  const map = useMap()
  const layerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }

    const group = L.layerGroup()

    if (orderGeometry) {
      L.geoJSON(orderGeometry as GeoJSON.GeoJsonObject, {
        style: () => ORDER_STYLE,
        interactive: false,
      }).addTo(group)
    }

    for (const track of tracks) {
      if (track.buffer_geometry) {
        L.geoJSON(track.buffer_geometry as GeoJSON.GeoJsonObject, {
          style: () => BUFFER_STYLE,
          interactive: false,
        }).addTo(group)
      }
      if (track.geometry) {
        L.geoJSON(track.geometry as GeoJSON.GeoJsonObject, {
          style: () => TRACK_STYLE,
          interactive: false,
        }).addTo(group)
      }
    }

    for (const task of tasks) {
      if (!task.geometry) continue
      const selected = task.task_key === selectedTaskKey
      const taskKey = task.task_key
      L.geoJSON(task.geometry as GeoJSON.GeoJsonObject, {
        style: () => ({
          ...TASK_PATH_STYLE,
          color: selected ? '#e65100' : TASK_PATH_STYLE.color,
          fillColor: selected ? '#ff9800' : TASK_PATH_STYLE.fillColor,
          weight: selected ? 3 : 2,
        }),
        pointToLayer: (_feature, latlng) =>
          L.circleMarker(latlng, {
            ...TASK_PATH_STYLE,
            color: selected ? '#e65100' : TASK_PATH_STYLE.color,
            fillColor: selected ? '#ff9800' : TASK_PATH_STYLE.fillColor,
            radius: selected ? 8 : TASK_POINT_RADIUS,
          }),
        onEachFeature: (_feature, layer) => {
          layer.on('click', (e) => {
            L.DomEvent.stopPropagation(e)
            onSelectTask?.(taskKey)
          })
        },
        interactive: true,
      }).addTo(group)
    }

    group.addTo(map)
    layerRef.current = group

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, orderGeometry, tasks, tracks, selectedTaskKey, onSelectTask])

  return null
}

export function FieldScoreMapView({
  orderGeometry,
  tasks,
  tracks,
  selectedTaskKey,
  onSelectTask,
}: FieldScoreMapViewProps) {
  return (
    <MapContainer
      center={MOSCOW_CENTER}
      zoom={11}
      maxZoom={MAP_MAX_ZOOM}
      className="map-container"
      attributionControl={false}
    >
      <BasemapLayers />
      <AttributionControl position="bottomright" prefix={LEAFLET_ATTRIBUTION_PREFIX} />
      <MapResizeObserver />
      <FitLayers orderGeometry={orderGeometry} tasks={tasks} tracks={tracks} />
      <ScoreLayers
        orderGeometry={orderGeometry}
        tasks={tasks}
        tracks={tracks}
        selectedTaskKey={selectedTaskKey}
        onSelectTask={onSelectTask}
      />
    </MapContainer>
  )
}
