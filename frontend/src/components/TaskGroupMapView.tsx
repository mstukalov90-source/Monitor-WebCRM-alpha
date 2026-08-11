import { useEffect, useRef } from 'react'
import { AttributionControl, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { BasemapLayers } from './BasemapLayers'
import { MapResizeObserver } from './MapResizeObserver'
import type { TaskGroupMapFeature } from '../types'

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

const GROUP_PATH_STYLE: L.PathOptions = {
  color: '#455a64',
  weight: 2,
  fillColor: '#90a4ae',
  fillOpacity: 0.35,
}

const SELECTED_PATH_STYLE: L.PathOptions = {
  color: '#e65100',
  weight: 3,
  fillColor: '#ff9800',
  fillOpacity: 0.45,
}

const POINT_RADIUS = 6

interface TaskGroupMapViewProps {
  features: TaskGroupMapFeature[]
  selectedTaskKey: string | null
}

function FitFeatures({ features }: { features: TaskGroupMapFeature[] }) {
  const map = useMap()

  useEffect(() => {
    const layers: L.Layer[] = []
    for (const feature of features) {
      if (feature.geometry) {
        layers.push(L.geoJSON(feature.geometry as GeoJSON.GeoJsonObject))
      }
    }
    if (!layers.length) return
    const group = L.featureGroup(layers)
    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 17 })
    }
  }, [map, features])

  return null
}

function GroupLayers({ features, selectedTaskKey }: TaskGroupMapViewProps) {
  const map = useMap()
  const layerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }

    const group = L.layerGroup()
    for (const feature of features) {
      if (!feature.geometry) continue
      const selected = feature.task_key === selectedTaskKey
      const style = selected ? SELECTED_PATH_STYLE : GROUP_PATH_STYLE
      L.geoJSON(feature.geometry as GeoJSON.GeoJsonObject, {
        style: () => style,
        pointToLayer: (_feat, latlng) =>
          L.circleMarker(latlng, {
            ...style,
            radius: selected ? 8 : POINT_RADIUS,
          }),
        interactive: false,
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
  }, [map, features, selectedTaskKey])

  return null
}

export function TaskGroupMapView({ features, selectedTaskKey }: TaskGroupMapViewProps) {
  return (
    <MapContainer
      center={MOSCOW_CENTER}
      zoom={11}
      maxZoom={MAP_MAX_ZOOM}
      className="task-group-map-container"
      attributionControl={false}
    >
      <BasemapLayers />
      <AttributionControl position="bottomright" prefix={LEAFLET_ATTRIBUTION_PREFIX} />
      <MapResizeObserver />
      <FitFeatures features={features} />
      <GroupLayers features={features} selectedTaskKey={selectedTaskKey} />
    </MapContainer>
  )
}
