import { useCallback, useRef } from 'react'

export interface DragResizeOptions {
  orientation: 'vertical' | 'horizontal'
  onResize: (delta: number) => void
  onResizeStart?: () => void
  onResizeEnd?: () => void
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function useDragResize({
  orientation,
  onResize,
  onResizeStart,
  onResizeEnd,
}: DragResizeOptions) {
  const draggingRef = useRef(false)
  const startPosRef = useRef(0)

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      event.preventDefault()
      draggingRef.current = true
      startPosRef.current = orientation === 'vertical' ? event.clientX : event.clientY
      event.currentTarget.setPointerCapture(event.pointerId)
      document.body.style.userSelect = 'none'
      document.body.style.cursor = orientation === 'vertical' ? 'col-resize' : 'row-resize'
      onResizeStart?.()
    },
    [orientation, onResizeStart],
  )

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (!draggingRef.current) return
      const current = orientation === 'vertical' ? event.clientX : event.clientY
      const delta = current - startPosRef.current
      startPosRef.current = current
      onResize(delta)
    },
    [orientation, onResize],
  )

  const endDrag = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (!draggingRef.current) return
      draggingRef.current = false
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId)
      }
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      onResizeEnd?.()
    },
    [onResizeEnd],
  )

  return {
    handlePointerDown,
    handlePointerMove,
    handlePointerUp: endDrag,
    handlePointerCancel: endDrag,
  }
}

export { clamp }
