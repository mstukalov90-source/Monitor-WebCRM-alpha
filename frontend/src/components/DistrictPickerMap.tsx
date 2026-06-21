import { useEffect, useMemo, useRef, useState } from 'react'
import { AttributionControl, MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchGeoJson, fetchLayersConfig } from '../api/client'
import type { LayerGroupConfig } from '../types'
import {
  DISTRICT_RAYON_FIELD,
  filterDistrictGeoJson,
  HOOD_BOUNDARIES_DISPLAY_NAME,
  MOSCOW_MAP_BBOX,
  normalizeRayonName,
  resolveRayonFromDistricts,
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

const HOOD_STYLE_DEFAULT: L.PathOptions = {
  color: '#cc0000',
  weight: 2,
  fillColor: '#ff6666',
  fillOpacity: 0.08,
}

const HOOD_STYLE_SELECTED: L.PathOptions = {
  color: '#0d6efd',
  weight: 3,
  fillColor: '#0d6efd',
  fillOpacity: 0.25,
}

interface DistrictPickerMapProps {
  selectedRayon: string
  districts: string[]
  onRayonSelect: (rayon: string) => void
  disabled?: boolean
}

function findHoodLayerKey(groups: LayerGroupConfig[]): string | null {
  for (const group of groups) {
    for (const layer of group.layers) {
      if (layer.display_name === HOOD_BOUNDARIES_DISPLAY_NAME) {
        return layer.layer_key
      }
    }
    if (group.groups.length) {
      const nested = findHoodLayerKey(group.groups)
      if (nested) return nested
    }
  }
  return null
}

function HoodDistrictsLayer({
  layerKey,
  selectedRayon,
  districts,
  onRayonSelect,
  disabled,
}: {
  layerKey: string | null
  selectedRayon: string
  districts: string[]
  onRayonSelect: (rayon: string) => void
  disabled?: boolean
}) {
  const map = useMap()
  const layerRef = useRef<L.GeoJSON | null>(null)
  const selectedNorm = useMemo(() => normalizeRayonName(selectedRayon), [selectedRayon])

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (!layerKey) return

    let cancelled = false
    fetchGeoJson(layerKey, MOSCOW_MAP_BBOX, 500)
      .then((geojson) => {
        if (cancelled) return

        const filtered = filterDistrictGeoJson(geojson)

        const gj = L.geoJSON(filtered, {
          style: (feature) => {
            const raw = feature?.properties?.[DISTRICT_RAYON_FIELD]
            const isSelected =
              selectedNorm !== '' &&
              normalizeRayonName(String(raw ?? '')) === selectedNorm
            return isSelected ? HOOD_STYLE_SELECTED : HOOD_STYLE_DEFAULT
          },
          onEachFeature: (feature, pathLayer) => {
            const raw = feature.properties?.[DISTRICT_RAYON_FIELD]
            const label = normalizeRayonName(String(raw ?? '')) || 'Район'
            pathLayer.bindTooltip(label, { sticky: true, opacity: 0.9 })

            pathLayer.on('click', () => {
              if (disabled) return
              const resolved = resolveRayonFromDistricts(raw, districts)
              if (resolved) onRayonSelect(resolved)
            })
          },
        })

        gj.addTo(map)
        layerRef.current = gj

        const bounds = gj.getBounds()
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [24, 24] })
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
  }, [map, layerKey, districts, onRayonSelect, disabled])

  useEffect(() => {
    const gj = layerRef.current
    if (!gj) return

    gj.eachLayer((pathLayer) => {
      const layer = pathLayer as L.Path
      const feature = (pathLayer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      const raw = feature?.properties?.[DISTRICT_RAYON_FIELD]
      const isSelected =
        selectedNorm !== '' && normalizeRayonName(String(raw ?? '')) === selectedNorm
      layer.setStyle(isSelected ? HOOD_STYLE_SELECTED : HOOD_STYLE_DEFAULT)
      if (isSelected && 'bringToFront' in layer && typeof layer.bringToFront === 'function') {
        layer.bringToFront()
      }
    })

    if (selectedNorm) {
      const selectedLayers: L.Layer[] = []
      gj.eachLayer((pathLayer) => {
        const feature = (pathLayer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
        const raw = feature?.properties?.[DISTRICT_RAYON_FIELD]
        if (normalizeRayonName(String(raw ?? '')) === selectedNorm) {
          selectedLayers.push(pathLayer)
        }
      })
      if (selectedLayers.length) {
        const group = L.featureGroup(selectedLayers)
        const bounds = group.getBounds()
        if (bounds.isValid()) {
          map.flyToBounds(bounds, { padding: [48, 48], maxZoom: 13 })
        }
      }
    }
  }, [selectedNorm, map])

  return null
}

export function DistrictPickerMap({
  selectedRayon,
  districts,
  onRayonSelect,
  disabled,
}: DistrictPickerMapProps) {
  const [layerKey, setLayerKey] = useState<string | null>(null)

  useEffect(() => {
    fetchLayersConfig()
      .then((cfg) => setLayerKey(findHoodLayerKey(cfg.groups)))
      .catch(() => setLayerKey(null))
  }, [])

  return (
    <div className="district-map">
      <p className="district-map-hint">Или выберите район на карте</p>
      <MapContainer
        center={MOSCOW_CENTER}
        zoom={10}
        maxZoom={MAP_MAX_ZOOM}
        className="district-map-container"
        attributionControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          maxZoom={MAP_MAX_ZOOM}
        />
        <AttributionControl position="bottomright" prefix={LEAFLET_ATTRIBUTION_PREFIX} />
        <HoodDistrictsLayer
          layerKey={layerKey}
          selectedRayon={selectedRayon}
          districts={districts}
          onRayonSelect={onRayonSelect}
          disabled={disabled}
        />
      </MapContainer>
      {!layerKey && <div className="district-map-fallback">Слой границ районов недоступен</div>}
    </div>
  )
}
