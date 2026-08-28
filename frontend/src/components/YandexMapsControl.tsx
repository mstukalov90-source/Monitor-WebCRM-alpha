import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import { yandexMapsUrlFromView } from '../lib/yandexMaps'

export function YandexMapsControl() {
  const map = useMap()

  useEffect(() => {
    const control = new L.Control({ position: 'bottomright' })
    control.onAdd = (mapInstance) => {
      const container = L.DomUtil.create('div', 'leaflet-control yandex-maps-control')
      const button = L.DomUtil.create('button', 'yandex-maps-control-btn', container)
      button.type = 'button'
      button.textContent = 'Яндекс.Карты'
      button.title = 'Открыть текущую область в Яндекс.Картах'

      L.DomEvent.disableClickPropagation(container)
      L.DomEvent.disableScrollPropagation(container)
      L.DomEvent.on(button, 'click', () => {
        const bounds = mapInstance.getBounds()
        const url = yandexMapsUrlFromView(
          {
            west: bounds.getWest(),
            south: bounds.getSouth(),
            east: bounds.getEast(),
            north: bounds.getNorth(),
          },
          mapInstance.getZoom(),
        )
        window.open(url, '_blank', 'noopener,noreferrer')
      })

      return container
    }
    control.addTo(map)
    return () => {
      control.remove()
    }
  }, [map])

  return null
}
