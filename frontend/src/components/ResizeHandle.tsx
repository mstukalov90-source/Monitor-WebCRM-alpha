import { useDragResize } from '../hooks/useDragResize'

interface ResizeHandleProps {
  orientation: 'vertical' | 'horizontal'
  onResize: (delta: number) => void
  onResizeStart?: () => void
  onResizeEnd?: () => void
}

export function ResizeHandle({ orientation, onResize, onResizeStart, onResizeEnd }: ResizeHandleProps) {
  const { handlePointerDown, handlePointerMove, handlePointerUp, handlePointerCancel } = useDragResize({
    orientation,
    onResize,
    onResizeStart,
    onResizeEnd,
  })

  return (
    <div
      className={`resize-handle resize-handle--${orientation}`}
      role="separator"
      aria-orientation={orientation === 'vertical' ? 'vertical' : 'horizontal'}
      aria-label={orientation === 'vertical' ? 'Изменить ширину панели' : 'Изменить высоту легенды'}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
    />
  )
}
