import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'

export const DEFAULT_SIDEBAR_WIDTH = 380
export const DEFAULT_LEGEND_HEIGHT = 160
export const SIDEBAR_WIDTH_MIN = 260
/** Legend always uses 20% of map-area height (map keeps ~80%). */
export const LEGEND_HEIGHT_RATIO = 0.2

export function clampSidebarWidth(width: number, containerWidth: number): number {
  const max = Math.round(containerWidth * 0.55)
  return Math.min(max, Math.max(SIDEBAR_WIDTH_MIN, width))
}

export function legendHeightForMapArea(mapAreaHeight: number): number {
  if (mapAreaHeight <= 0) return DEFAULT_LEGEND_HEIGHT
  return Math.round(mapAreaHeight * LEGEND_HEIGHT_RATIO)
}

export function sidebarScale(width: number): number {
  return Math.min(1.25, Math.max(0.75, width / DEFAULT_SIDEBAR_WIDTH))
}

export function legendScale(height: number): number {
  return Math.min(1.25, Math.max(0.75, height / DEFAULT_LEGEND_HEIGHT))
}

export function useWorkspaceLayout() {
  const appBodyRef = useRef<HTMLDivElement>(null)
  const mapAreaRef = useRef<HTMLElement>(null)
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH)
  const [mapAreaHeight, setMapAreaHeight] = useState(0)
  const [resizing, setResizing] = useState(false)

  const legendHeight = legendHeightForMapArea(mapAreaHeight)

  const measureMapArea = useCallback(() => {
    const el = mapAreaRef.current
    if (!el) return
    setMapAreaHeight(el.clientHeight)
  }, [])

  const handleSidebarResize = useCallback((delta: number) => {
    const containerWidth = appBodyRef.current?.clientWidth ?? window.innerWidth
    setSidebarWidth((prev) => clampSidebarWidth(prev + delta, containerWidth))
  }, [])

  useEffect(() => {
    const el = mapAreaRef.current
    if (!el) return
    measureMapArea()
    const observer = new ResizeObserver(measureMapArea)
    observer.observe(el)
    return () => observer.disconnect()
  }, [measureMapArea])

  const layoutStyle = {
    '--sidebar-width': `${sidebarWidth}px`,
    '--legend-height': `${legendHeight}px`,
    '--sidebar-scale': String(sidebarScale(sidebarWidth)),
    '--legend-scale': String(legendScale(legendHeight)),
  } as CSSProperties

  return {
    appBodyRef,
    mapAreaRef,
    resizing,
    setResizing,
    layoutStyle,
    handleSidebarResize,
  }
}
