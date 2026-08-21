import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'

export const DEFAULT_SIDEBAR_WIDTH = 380
export const DEFAULT_LEGEND_HEIGHT = 160
export const SIDEBAR_WIDTH_MIN = 260
export const MAP_AREA_WIDTH_MIN = 240
export const TASK_EDIT_WIDTH_STORAGE_KEY = 'webcrm.task-edit-width'
/** Legend always uses 20% of map-area height (map keeps ~80%). */
export const LEGEND_HEIGHT_RATIO = 0.2

function readStoredWidth(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key)
    if (raw == null) return fallback
    const value = Number(raw)
    return Number.isFinite(value) ? value : fallback
  } catch {
    return fallback
  }
}

function writeStoredWidth(key: string, width: number) {
  try {
    localStorage.setItem(key, String(Math.round(width)))
  } catch {
    /* ignore quota / private mode */
  }
}

export function clampSidebarWidth(width: number, containerWidth: number): number {
  const max = Math.round(containerWidth * 0.55)
  return Math.min(max, Math.max(SIDEBAR_WIDTH_MIN, width))
}

export function clampTaskEditWidth(
  width: number,
  containerWidth: number,
  sidebarWidth: number,
): number {
  const maxRatio = Math.round(containerWidth * 0.55)
  const maxLayout = containerWidth - sidebarWidth - MAP_AREA_WIDTH_MIN
  const max = Math.max(SIDEBAR_WIDTH_MIN, Math.min(maxRatio, maxLayout))
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
  const [taskEditWidth, setTaskEditWidth] = useState(() =>
    clampTaskEditWidth(
      readStoredWidth(TASK_EDIT_WIDTH_STORAGE_KEY, DEFAULT_SIDEBAR_WIDTH),
      typeof window !== 'undefined' ? window.innerWidth : DEFAULT_SIDEBAR_WIDTH * 3,
      DEFAULT_SIDEBAR_WIDTH,
    ),
  )
  const [mapAreaHeight, setMapAreaHeight] = useState(0)
  const [resizing, setResizing] = useState(false)
  const sidebarWidthRef = useRef(sidebarWidth)
  sidebarWidthRef.current = sidebarWidth

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

  const handleTaskEditResize = useCallback((delta: number) => {
    const containerWidth = appBodyRef.current?.clientWidth ?? window.innerWidth
    setTaskEditWidth((prev) => {
      const next = clampTaskEditWidth(prev - delta, containerWidth, sidebarWidthRef.current)
      writeStoredWidth(TASK_EDIT_WIDTH_STORAGE_KEY, next)
      return next
    })
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
    '--task-edit-width': `${taskEditWidth}px`,
    '--legend-height': `${legendHeight}px`,
    '--sidebar-scale': String(sidebarScale(sidebarWidth)),
    '--task-edit-scale': String(sidebarScale(taskEditWidth)),
    '--legend-scale': String(legendScale(legendHeight)),
  } as CSSProperties

  return {
    appBodyRef,
    mapAreaRef,
    resizing,
    setResizing,
    layoutStyle,
    handleSidebarResize,
    handleTaskEditResize,
  }
}
