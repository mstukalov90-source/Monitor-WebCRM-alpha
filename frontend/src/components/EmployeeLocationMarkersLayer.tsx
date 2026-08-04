import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import { employeeLocationMarkerStyle } from '../lib/employeeLocationStyle'
import type { EmployeeLocationFeature } from '../types'

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
          updatedAt: loc.attributes.time ?? null,
        },
        geometry: loc.geometry,
      }))

    if (!features.length) return

    const gj = L.geoJSON(
      { type: 'FeatureCollection', features } as GeoJSON.FeatureCollection,
      {
        pointToLayer: (feature, latlng) =>
          L.circleMarker(latlng, {
            ...employeeLocationMarkerStyle(feature?.properties?.updatedAt),
            interactive: false,
          }),
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
