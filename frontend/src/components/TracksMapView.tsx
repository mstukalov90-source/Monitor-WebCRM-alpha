import { useEffect, useRef, useState } from 'react'
import { AttributionControl, MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchGeoJson, fetchLayersConfig } from '../api/client'
import { findHoodLayerKey } from '../lib/hoodLayer'
import { MapResizeObserver } from './MapResizeObserver'
import type { TrackFeature } from '../types'
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

const TRACK_STYLE_DEFAULT: L.PathOptions = {
  color: '#0d6efd',
  weight: 3,
  opacity: 0.85,
}

const TRACK_STYLE_SELECTED: L.PathOptions = {
  color: '#ff6600',
  weight: 5,
  opacity: 1,
}

interface TracksMapViewProps {
  tracks: TrackFeature[]
  districtName: string
  selectedTrackId: string | null
  onSelectTrack: (trackId: string) => void
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

function TracksLayer({
  tracks,
  selectedTrackId,
  onSelectTrack,
}: {
  tracks: TrackFeature[]
  selectedTrackId: string | null
  onSelectTrack: (trackId: string) => void
}) {
  const map = useMap()
  const layerRef = useRef<L.GeoJSON | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }

    const features: GeoJSON.Feature[] = tracks
      .filter((t) => t.geometry)
      .map((t) => ({
        type: 'Feature' as const,
        properties: { trackId: t.id },
        geometry: t.geometry,
      }))

    if (!features.length) return

    const gj = L.geoJSON(
      { type: 'FeatureCollection', features } as GeoJSON.FeatureCollection,
      {
        style: (feature) => {
          const trackId = String(feature?.properties?.trackId ?? '')
          return trackId === selectedTrackId ? TRACK_STYLE_SELECTED : TRACK_STYLE_DEFAULT
        },
        onEachFeature: (feature, pathLayer) => {
          const trackId = String(feature.properties?.trackId ?? '')
          pathLayer.on('click', () => {
            if (trackId) onSelectTrack(trackId)
          })
        },
      },
    )
    gj.addTo(map)
    layerRef.current = gj

    const bounds = gj.getBounds()
    if (bounds.isValid() && !selectedTrackId) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, tracks, selectedTrackId, onSelectTrack])

  useEffect(() => {
    const gj = layerRef.current
    if (!gj || !selectedTrackId) return

    gj.eachLayer((pathLayer) => {
      const layer = pathLayer as L.Path
      const feature = (pathLayer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      const trackId = String(feature?.properties?.trackId ?? '')
      layer.setStyle(trackId === selectedTrackId ? TRACK_STYLE_SELECTED : TRACK_STYLE_DEFAULT)
      if (trackId === selectedTrackId && 'bringToFront' in layer) {
        layer.bringToFront()
      }
    })

    const selectedLayers: L.Layer[] = []
    gj.eachLayer((pathLayer) => {
      const feature = (pathLayer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      if (String(feature?.properties?.trackId ?? '') === selectedTrackId) {
        selectedLayers.push(pathLayer)
      }
    })
    if (selectedLayers.length) {
      const group = L.featureGroup(selectedLayers)
      const bounds = group.getBounds()
      if (bounds.isValid()) {
        map.flyToBounds(bounds, { padding: [48, 48], maxZoom: 17 })
      }
    }
  }, [map, selectedTrackId])

  return null
}

export function TracksMapView({
  tracks,
  districtName,
  selectedTrackId,
  onSelectTrack,
}: TracksMapViewProps) {
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
      <DistrictBoundaryLayer districtName={districtName} />
      <TracksLayer tracks={tracks} selectedTrackId={selectedTrackId} onSelectTrack={onSelectTrack} />
    </MapContainer>
  )
}
