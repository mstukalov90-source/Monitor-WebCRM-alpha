import { useEffect, useMemo, useRef, useState } from 'react'
import { AttributionControl, MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchGeoJson, fetchLayersConfig } from '../api/client'
import { EmployeeLocationMarkersLayer } from './EmployeeLocationMarkersLayer'
import { createAreaSvgRenderer, hatchFillStyle } from '../lib/areaMapStyle'
import {
  buildDistrictOrdersPopupHtml,
  ordersForRayon,
  type AreaOrdersByRayon,
} from '../lib/areaOrders'
import {
  buildDistrictStyleByRayon,
  districtBasePathStyle,
  type DistrictOrderVisual,
} from '../lib/districtOrderStyle'
import {
  extractDistrictMeta,
  filterDistrictGeoJsonByOkrug,
  findHoodLayerKey,
  type DistrictHoodMeta,
} from '../lib/hoodLayer'
import type { EmployeeLocationFeature } from '../types'
import {
  DISTRICT_RAYON_FIELD,
  filterDistrictGeoJson,
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

const EMPTY_VISUAL: DistrictOrderVisual = { fill: 'empty', hatch: 'none' }

interface DistrictPickerMapProps {
  selectedRayon: string
  selectedOkrug?: string
  districts: string[]
  onRayonSelect: (rayon: string) => void
  onHoodMeta?: (meta: DistrictHoodMeta) => void
  disabled?: boolean
  employeeLocations?: EmployeeLocationFeature[]
  areaOrdersByRayon?: AreaOrdersByRayon[]
  /** When false, use legacy red styling until orders finish loading. */
  areaOrdersReady?: boolean
}

type DistrictPath = L.Path & {
  feature?: GeoJSON.Feature
  _districtRayon?: string
  _districtVisual?: DistrictOrderVisual
}

function resolveVisual(
  rayonNorm: string,
  styleByRayon: Map<string, DistrictOrderVisual>,
  areaOrdersReady: boolean,
): DistrictOrderVisual | null {
  if (!areaOrdersReady) return null
  return styleByRayon.get(rayonNorm) ?? EMPTY_VISUAL
}

function baseStyleFor(
  visual: DistrictOrderVisual | null,
  selected: boolean,
): L.PathOptions {
  if (!visual) {
    return selected ? HOOD_STYLE_SELECTED : HOOD_STYLE_DEFAULT
  }
  return districtBasePathStyle(visual, selected)
}

function HoodDistrictsLayer({
  layerKey,
  selectedRayon,
  selectedOkrug,
  districts,
  onRayonSelect,
  onHoodMeta,
  disabled,
  styleByRayon,
  areaOrdersByRayon,
  areaOrdersReady,
}: {
  layerKey: string | null
  selectedRayon: string
  selectedOkrug: string
  districts: string[]
  onRayonSelect: (rayon: string) => void
  onHoodMeta?: (meta: DistrictHoodMeta) => void
  disabled?: boolean
  styleByRayon: Map<string, DistrictOrderVisual>
  areaOrdersByRayon: AreaOrdersByRayon[]
  areaOrdersReady: boolean
}) {
  const map = useMap()
  const baseGroupRef = useRef<L.FeatureGroup | null>(null)
  const hatchGroupRef = useRef<L.FeatureGroup | null>(null)
  const rendererRef = useRef<L.SVG | null>(null)
  const metaReportedRef = useRef(false)
  const selectedNorm = useMemo(() => normalizeRayonName(selectedRayon), [selectedRayon])
  const selectedNormRef = useRef(selectedNorm)
  selectedNormRef.current = selectedNorm
  const onHoodMetaRef = useRef(onHoodMeta)
  onHoodMetaRef.current = onHoodMeta
  const areaOrdersRef = useRef(areaOrdersByRayon)
  areaOrdersRef.current = areaOrdersByRayon

  useEffect(() => {
    if (baseGroupRef.current) {
      map.removeLayer(baseGroupRef.current)
      baseGroupRef.current = null
    }
    if (hatchGroupRef.current) {
      map.removeLayer(hatchGroupRef.current)
      hatchGroupRef.current = null
    }
    if (rendererRef.current) {
      map.removeLayer(rendererRef.current)
      rendererRef.current = null
    }
    if (!layerKey) return

    let cancelled = false
    fetchGeoJson(layerKey, MOSCOW_MAP_BBOX, 500)
      .then((geojson) => {
        if (cancelled) return

        if (!metaReportedRef.current) {
          metaReportedRef.current = true
          onHoodMetaRef.current?.(extractDistrictMeta(geojson))
        }

        const filtered = filterDistrictGeoJsonByOkrug(
          filterDistrictGeoJson(geojson),
          selectedOkrug,
        )
        const renderer = createAreaSvgRenderer(map)
        rendererRef.current = renderer

        const baseGroup = L.featureGroup()
        const hatchGroup = L.featureGroup()
        const currentSelected = selectedNormRef.current

        for (const feature of filtered.features) {
          const raw = feature.properties?.[DISTRICT_RAYON_FIELD]
          const rayonNorm = normalizeRayonName(String(raw ?? ''))
          const visual = resolveVisual(rayonNorm, styleByRayon, areaOrdersReady)
          const isSelected = currentSelected !== '' && rayonNorm === currentSelected
          const single = {
            type: 'FeatureCollection',
            features: [feature],
          } as GeoJSON.FeatureCollection

          const popupHtml = buildDistrictOrdersPopupHtml(
            rayonNorm || 'Район',
            ordersForRayon(areaOrdersRef.current, rayonNorm),
          )

          const baseGj = L.geoJSON(single, {
            renderer,
            style: () => baseStyleFor(visual, isSelected),
            onEachFeature: (_f, pathLayer) => {
              const path = pathLayer as DistrictPath
              path._districtRayon = rayonNorm
              path._districtVisual = visual ?? undefined
              const label = rayonNorm || 'Район'
              path.bindTooltip(label, { sticky: true, opacity: 0.9 })
              path.bindPopup(popupHtml, {
                maxWidth: 360,
                className: 'district-orders-popup',
                autoPanPadding: [24, 24],
              })
              path.on('click', () => {
                if (disabled) return
                const resolved = resolveRayonFromDistricts(raw, districts)
                if (resolved) onRayonSelect(resolved)
              })
            },
          } as L.GeoJSONOptions)
          baseGj.eachLayer((layer) => baseGroup.addLayer(layer))

          if (visual && visual.hatch !== 'none') {
            const hatchKind = visual.hatch
            const hatchGj = L.geoJSON(single, {
              renderer,
              interactive: false,
              style: () => hatchFillStyle(hatchKind),
            } as L.GeoJSONOptions)
            hatchGj.eachLayer((layer) => hatchGroup.addLayer(layer))
          }
        }

        baseGroup.addTo(map)
        hatchGroup.addTo(map)
        baseGroupRef.current = baseGroup
        hatchGroupRef.current = hatchGroup

        const bounds = baseGroup.getBounds()
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [24, 24] })
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (baseGroupRef.current) {
        map.removeLayer(baseGroupRef.current)
        baseGroupRef.current = null
      }
      if (hatchGroupRef.current) {
        map.removeLayer(hatchGroupRef.current)
        hatchGroupRef.current = null
      }
      if (rendererRef.current) {
        map.removeLayer(rendererRef.current)
        rendererRef.current = null
      }
    }
  }, [
    map,
    layerKey,
    selectedOkrug,
    districts,
    onRayonSelect,
    disabled,
    styleByRayon,
    areaOrdersReady,
    areaOrdersByRayon,
  ])

  useEffect(() => {
    const baseGroup = baseGroupRef.current
    if (!baseGroup) return

    baseGroup.eachLayer((pathLayer) => {
      const path = pathLayer as DistrictPath
      const rayonNorm = path._districtRayon ?? ''
      const visual = path._districtVisual ?? null
      const isSelected = selectedNorm !== '' && rayonNorm === selectedNorm
      path.setStyle(baseStyleFor(visual, isSelected))
      if (isSelected && typeof path.bringToFront === 'function') {
        path.bringToFront()
      }
    })

    hatchGroupRef.current?.eachLayer((layer) => {
      if ('bringToFront' in layer && typeof layer.bringToFront === 'function') {
        layer.bringToFront()
      }
    })

    if (!selectedNorm) return

    const selectedLayers: L.Layer[] = []
    baseGroup.eachLayer((pathLayer) => {
      const path = pathLayer as DistrictPath
      if (path._districtRayon === selectedNorm) {
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
  }, [selectedNorm, map])

  return null
}

export function DistrictPickerMap({
  selectedRayon,
  selectedOkrug = '',
  districts,
  onRayonSelect,
  onHoodMeta,
  disabled,
  employeeLocations = [],
  areaOrdersByRayon = [],
  areaOrdersReady = false,
}: DistrictPickerMapProps) {
  const [layerKey, setLayerKey] = useState<string | null>(null)

  const styleByRayon = useMemo(
    () => buildDistrictStyleByRayon(areaOrdersByRayon),
    [areaOrdersByRayon],
  )

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
          selectedOkrug={selectedOkrug}
          districts={districts}
          onRayonSelect={onRayonSelect}
          onHoodMeta={onHoodMeta}
          disabled={disabled}
          styleByRayon={styleByRayon}
          areaOrdersByRayon={areaOrdersByRayon}
          areaOrdersReady={areaOrdersReady}
        />
        {employeeLocations.length > 0 && (
          <EmployeeLocationMarkersLayer locations={employeeLocations} />
        )}
      </MapContainer>
      {!layerKey && <div className="district-map-fallback">Слой границ районов недоступен</div>}
    </div>
  )
}
