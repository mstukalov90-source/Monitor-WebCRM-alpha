import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import type { EmployeeLocationFeature } from '../types'

const MARKER_STYLE: L.CircleMarkerOptions = {
  radius: 8,
  color: '#0d6efd',
  weight: 2,
  fillColor: '#0d6efd',
  fillOpacity: 0.85,
  interactive: false,
}

interface EmployeeLocationMarkersLayerProps {
  locations: EmployeeLocationFeature[]
}

export function EmployeeLocationMarkersLayer({ locations }: EmployeeLocationMarkersLayerProps) {
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
        properties: {
          label: String(loc.attributes.user ?? loc.id),
        },
        geometry: loc.geometry,
      }))

    if (!features.length) return

    const gj = L.geoJSON(
      { type: 'FeatureCollection', features } as GeoJSON.FeatureCollection,
      {
        pointToLayer: (_feature, latlng) => L.circleMarker(latlng, MARKER_STYLE),
        onEachFeature: (feature, layer) => {
          const label = String(feature.properties?.label ?? '')
          if (label) {
            layer.bindTooltip(label, { direction: 'top', opacity: 0.9 })
          }
        },
      },
    )
    gj.addTo(map)
    layerRef.current = gj

    gj.eachLayer((markerLayer) => {
      if ('bringToFront' in markerLayer && typeof markerLayer.bringToFront === 'function') {
        markerLayer.bringToFront()
      }
    })

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [map, locations])

  return null
}
