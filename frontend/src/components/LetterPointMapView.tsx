import { useEffect, useRef } from 'react'
import { AttributionControl, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { BasemapLayers } from './BasemapLayers'
import { MapResizeObserver } from './MapResizeObserver'

const MAP_MAX_ZOOM = 19

const RUSSIAN_FLAG_SVG =
  '<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="12" height="8" viewBox="0 0 12 8" class="leaflet-attribution-flag">' +
  '<path fill="#fff" d="M0 0h12v2.67H0z"/>' +
  '<path fill="#0039A6" d="M0 2.67h12v2.66H0z"/>' +
  '<path fill="#D52B1E" d="M0 5.33h12v2.67H0z"/>' +
  '</svg>'

const LEAFLET_ATTRIBUTION_PREFIX =
  `<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">${RUSSIAN_FLAG_SVG} Leaflet</a>`

interface LetterPointMapViewProps {
  lat: number | null
  lon: number | null
}

function FitPoint({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap()

  useEffect(() => {
    map.setView([lat, lon], 16)
  }, [map, lat, lon])

  return null
}

function PointLayer({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap()
  const layerRef = useRef<L.CircleMarker | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    const marker = L.circleMarker([lat, lon], {
      radius: 8,
      color: '#c62828',
      weight: 2,
      fillColor: '#ef5350',
      fillOpacity: 0.9,
    })
    marker.addTo(map)
    layerRef.current = marker
    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, lat, lon])

  return null
}

export function LetterPointMapView({ lat, lon }: LetterPointMapViewProps) {
  if (lat == null || lon == null) {
    return <p className="muted small">Нет координат точки письма</p>
  }

  return (
    <MapContainer
      center={[lat, lon]}
      zoom={16}
      maxZoom={MAP_MAX_ZOOM}
      className="map-container letter-review-map"
      attributionControl={false}
    >
      <BasemapLayers />
      <AttributionControl position="bottomright" prefix={LEAFLET_ATTRIBUTION_PREFIX} />
      <MapResizeObserver />
      <FitPoint lat={lat} lon={lon} />
      <PointLayer lat={lat} lon={lon} />
    </MapContainer>
  )
}
