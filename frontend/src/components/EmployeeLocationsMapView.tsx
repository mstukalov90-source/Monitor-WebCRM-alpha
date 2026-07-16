import { useEffect, useRef, useState } from 'react'
import { AttributionControl, MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchGeoJson, fetchLayersConfig } from '../api/client'
import { findHoodLayerKey } from '../lib/hoodLayer'
import { MapResizeObserver } from './MapResizeObserver'
import type { EmployeeLocationFeature } from '../types'
import {
  DISTRICT_RAYON_FIELD,
  filterDistrictGeoJson,
  MOSCOW_MAP_BBOX,
  normalizeRayonName,
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

const DISTRICT_BOUNDARY_STYLE: L.PathOptions = {
  color: '#cc0000',
  weight: 2,
  fillOpacity: 0,
}

const LOCATION_STYLE_DEFAULT: L.CircleMarkerOptions = {
  radius: 8,
  color: '#0d6efd',
  weight: 2,
  fillColor: '#0d6efd',
  fillOpacity: 0.85,
}

const LOCATION_STYLE_SELECTED: L.CircleMarkerOptions = {
  radius: 10,
  color: '#ff6600',
  weight: 3,
  fillColor: '#ff6600',
  fillOpacity: 1,
}

interface EmployeeLocationsMapViewProps {
  locations: EmployeeLocationFeature[]
  districtName?: string
  selectedLocationId: string | null
  onSelectLocation: (locationId: string) => void
}

function DistrictBoundaryLayer({ districtName }: { districtName: string }) {
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

function LocationsLayer({
  locations,
  selectedLocationId,
  onSelectLocation,
}: {
  locations: EmployeeLocationFeature[]
  selectedLocationId: string | null
  onSelectLocation: (locationId: string) => void
}) {
  const map = useMap()
  const layerRef = useRef<L.GeoJSON | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }

    const features: GeoJSON.Feature[] = locations
      .filter((loc) => loc.geometry)
      .map((loc) => ({
        type: 'Feature' as const,
        properties: { locationId: loc.id },
        geometry: loc.geometry,
      }))

    if (!features.length) return

    const gj = L.geoJSON(
      { type: 'FeatureCollection', features } as GeoJSON.FeatureCollection,
      {
        pointToLayer: (feature, latlng) => {
          const locationId = String(feature?.properties?.locationId ?? '')
          const style =
            locationId === selectedLocationId ? LOCATION_STYLE_SELECTED : LOCATION_STYLE_DEFAULT
          return L.circleMarker(latlng, style)
        },
        onEachFeature: (feature, layer) => {
          const locationId = String(feature.properties?.locationId ?? '')
          layer.on('click', () => {
            if (locationId) onSelectLocation(locationId)
          })
        },
      },
    )
    gj.addTo(map)
    layerRef.current = gj

    const bounds = gj.getBounds()
    if (bounds.isValid() && !selectedLocationId) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, locations, selectedLocationId, onSelectLocation])

  useEffect(() => {
    const gj = layerRef.current
    if (!gj) return

    gj.eachLayer((markerLayer) => {
      const layer = markerLayer as L.CircleMarker
      const feature = (markerLayer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      const locationId = String(feature?.properties?.locationId ?? '')
      const style =
        locationId === selectedLocationId ? LOCATION_STYLE_SELECTED : LOCATION_STYLE_DEFAULT
      layer.setStyle(style)
      if (locationId === selectedLocationId) {
        layer.bringToFront()
      }
    })

    if (!selectedLocationId) return

    const selectedLayers: L.Layer[] = []
    gj.eachLayer((markerLayer) => {
      const feature = (markerLayer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      if (String(feature?.properties?.locationId ?? '') === selectedLocationId) {
        selectedLayers.push(markerLayer)
      }
    })
    if (selectedLayers.length) {
      const group = L.featureGroup(selectedLayers)
      const bounds = group.getBounds()
      if (bounds.isValid()) {
        map.flyToBounds(bounds, { padding: [48, 48], maxZoom: 17 })
      }
    }
  }, [map, selectedLocationId])

  return null
}

export function EmployeeLocationsMapView({
  locations,
  districtName,
  selectedLocationId,
  onSelectLocation,
}: EmployeeLocationsMapViewProps) {
  return (
    <MapContainer
      center={MOSCOW_CENTER}
      zoom={11}
      maxZoom={MAP_MAX_ZOOM}
      className="map-container"
      attributionControl={false}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        maxZoom={MAP_MAX_ZOOM}
      />
      <AttributionControl position="bottomright" prefix={LEAFLET_ATTRIBUTION_PREFIX} />
      <MapResizeObserver />
      {districtName ? <DistrictBoundaryLayer districtName={districtName} /> : null}
      <LocationsLayer
        locations={locations}
        selectedLocationId={selectedLocationId}
        onSelectLocation={onSelectLocation}
      />
    </MapContainer>
  )
}
