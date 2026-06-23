import { useEffect } from 'react'
import { useMap } from 'react-leaflet'

export function MapResizeObserver() {
  const map = useMap()

  useEffect(() => {
    const container = map.getContainer()
    const viewport = container.closest('.map-viewport')
    if (!viewport) return

    const observer = new ResizeObserver(() => {
      map.invalidateSize()
    })
    observer.observe(viewport)

    return () => observer.disconnect()
  }, [map])

  return null
}
