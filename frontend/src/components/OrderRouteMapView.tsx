import { useEffect, useRef } from 'react'
import { AttributionControl, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { BasemapLayers } from './BasemapLayers'
import { MapResizeObserver } from './MapResizeObserver'

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

const ROUTE_STYLE: L.PathOptions = {
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

const UNCOVERED_STYLE: L.PathOptions = {
  color: '#c62828',
  weight: 1,
  fillColor: '#c62828',
  fillOpacity: 0.25,
  opacity: 0.7,
}

interface OrderRouteMapViewProps {
  orderGeometry: GeoJSON.Geometry | null | undefined
  routeGeometry?: GeoJSON.Geometry | null
  bufferGeometry?: GeoJSON.Geometry | null
  uncoveredGeometry?: GeoJSON.Geometry | null
}

function FitLayers({
  orderGeometry,
  routeGeometry,
}: {
  orderGeometry: GeoJSON.Geometry | null | undefined
  routeGeometry?: GeoJSON.Geometry | null
}) {
  const map = useMap()

  useEffect(() => {
    const layers: L.Layer[] = []
    if (orderGeometry) layers.push(L.geoJSON(orderGeometry as GeoJSON.GeoJsonObject))
    if (routeGeometry) layers.push(L.geoJSON(routeGeometry as GeoJSON.GeoJsonObject))
    if (!layers.length) return
    const group = L.featureGroup(layers)
    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }
  }, [map, orderGeometry, routeGeometry])

  return null
}

function RouteLayers({
  orderGeometry,
  routeGeometry,
  bufferGeometry,
  uncoveredGeometry,
}: OrderRouteMapViewProps) {
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
    if (bufferGeometry) {
      L.geoJSON(bufferGeometry as GeoJSON.GeoJsonObject, {
        style: () => BUFFER_STYLE,
        interactive: false,
      }).addTo(group)
    }
    if (uncoveredGeometry) {
      L.geoJSON(uncoveredGeometry as GeoJSON.GeoJsonObject, {
        style: () => UNCOVERED_STYLE,
        interactive: false,
      }).addTo(group)
    }
    if (routeGeometry) {
      L.geoJSON(routeGeometry as GeoJSON.GeoJsonObject, {
        style: () => ROUTE_STYLE,
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
  }, [map, orderGeometry, routeGeometry, bufferGeometry, uncoveredGeometry])

  return null
}

export function OrderRouteMapView({
  orderGeometry,
  routeGeometry,
  bufferGeometry,
  uncoveredGeometry,
}: OrderRouteMapViewProps) {
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
      <FitLayers orderGeometry={orderGeometry} routeGeometry={routeGeometry} />
      <RouteLayers
        orderGeometry={orderGeometry}
        routeGeometry={routeGeometry}
        bufferGeometry={bufferGeometry}
        uncoveredGeometry={uncoveredGeometry}
      />
    </MapContainer>
  )
}
