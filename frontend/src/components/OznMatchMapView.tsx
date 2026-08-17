import { useEffect, useRef } from 'react'
import { AttributionControl, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { BasemapLayers } from './BasemapLayers'
import { MapResizeObserver } from './MapResizeObserver'
import type { OznMatchObject, OznMatchOrder } from '../types'

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
  color: '#e65100',
  weight: 2,
  fillColor: '#ff9800',
  fillOpacity: 0.22,
}

const ORDER_SELECTED_STYLE: L.PathOptions = {
  color: '#bf360c',
  weight: 3,
  fillColor: '#ff6d00',
  fillOpacity: 0.4,
}

const ORDER_DIM_STYLE: L.PathOptions = {
  color: '#bcaaa4',
  weight: 1,
  fillColor: '#d7ccc8',
  fillOpacity: 0.12,
}

const OZN_STYLE: L.PathOptions = {
  color: '#1565c0',
  weight: 2,
  fillColor: '#42a5f5',
  fillOpacity: 0.28,
}

const OZN_SELECTED_STYLE: L.PathOptions = {
  color: '#0d47a1',
  weight: 3,
  fillColor: '#1976d2',
  fillOpacity: 0.45,
}

const OZN_DIM_STYLE: L.PathOptions = {
  color: '#90a4ae',
  weight: 1,
  fillColor: '#cfd8dc',
  fillOpacity: 0.1,
}

interface OznMatchMapViewProps {
  orders: OznMatchOrder[]
  oznObjects: OznMatchObject[]
  matches: Record<string, string[]>
  selectedOrderKey: string | null
  onSelectOrder: (orderKey: string) => void
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function FitSelection({
  orders,
  oznObjects,
  matches,
  selectedOrderKey,
}: {
  orders: OznMatchOrder[]
  oznObjects: OznMatchObject[]
  matches: Record<string, string[]>
  selectedOrderKey: string | null
}) {
  const map = useMap()

  useEffect(() => {
    const layers: L.Layer[] = []
    const selectedOzn = new Set(selectedOrderKey ? matches[selectedOrderKey] ?? [] : [])

    const ordersToFit = selectedOrderKey
      ? orders.filter((order) => order.order_key === selectedOrderKey)
      : orders
    const oznToFit = selectedOrderKey
      ? oznObjects.filter((item) => selectedOzn.has(item.id))
      : oznObjects

    for (const order of ordersToFit) {
      layers.push(L.geoJSON(order.geometry as GeoJSON.GeoJsonObject))
    }
    for (const item of oznToFit) {
      layers.push(L.geoJSON(item.geometry as GeoJSON.GeoJsonObject))
    }
    if (!layers.length) return
    const group = L.featureGroup(layers)
    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 })
    }
  }, [map, orders, oznObjects, matches, selectedOrderKey])

  return null
}

function MatchLayers({
  orders,
  oznObjects,
  matches,
  selectedOrderKey,
  onSelectOrder,
}: OznMatchMapViewProps) {
  const map = useMap()
  const layerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }

    const group = L.layerGroup()
    const selectedOzn = new Set(selectedOrderKey ? matches[selectedOrderKey] ?? [] : [])

    for (const item of oznObjects) {
      let style = OZN_STYLE
      if (selectedOrderKey) {
        style = selectedOzn.has(item.id) ? OZN_SELECTED_STYLE : OZN_DIM_STYLE
      }
      L.geoJSON(item.geometry as GeoJSON.GeoJsonObject, {
        style: () => style,
        onEachFeature: (_feature, layer) => {
          layer.bindPopup(`<b>ОЗН</b><br/>${escapeHtml(item.label)}`)
        },
      }).addTo(group)
    }

    for (const order of orders) {
      let style = ORDER_STYLE
      if (selectedOrderKey) {
        style = order.order_key === selectedOrderKey ? ORDER_SELECTED_STYLE : ORDER_DIM_STYLE
      }
      const title = order.task_number?.trim() || order.order_key.slice(0, 8)
      L.geoJSON(order.geometry as GeoJSON.GeoJsonObject, {
        style: () => style,
        onEachFeature: (_feature, layer) => {
          layer.bindPopup(
            `<b>Мониторинг</b><br/>${escapeHtml(title)}<br/>Пересечений: ${order.match_count}`,
          )
          layer.on('click', (e) => {
            L.DomEvent.stopPropagation(e)
            onSelectOrder(order.order_key)
          })
        },
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
  }, [map, orders, oznObjects, matches, selectedOrderKey, onSelectOrder])

  return null
}

export function OznMatchMapView({
  orders,
  oznObjects,
  matches,
  selectedOrderKey,
  onSelectOrder,
}: OznMatchMapViewProps) {
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
      <FitSelection
        orders={orders}
        oznObjects={oznObjects}
        matches={matches}
        selectedOrderKey={selectedOrderKey}
      />
      <MatchLayers
        orders={orders}
        oznObjects={oznObjects}
        matches={matches}
        selectedOrderKey={selectedOrderKey}
        onSelectOrder={onSelectOrder}
      />
    </MapContainer>
  )
}
