import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const MIN_SCALE = 1
const MAX_SCALE = 5
const WHEEL_STEP = 0.15
const BUTTON_STEP = 0.25

interface PhotoLightboxImageProps {
  src: string
  alt: string
  className?: string
  onError?: () => void
}

export function PhotoLightboxImage({ src, alt, className, onError }: PhotoLightboxImageProps) {
  const [open, setOpen] = useState(false)
  const [scale, setScale] = useState(MIN_SCALE)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const draggingRef = useRef(false)
  const movedRef = useRef(false)
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 })
  const stageRef = useRef<HTMLDivElement>(null)

  const resetView = useCallback(() => {
    setScale(MIN_SCALE)
    setPan({ x: 0, y: 0 })
  }, [])

  const close = useCallback(() => {
    setOpen(false)
    resetView()
  }, [resetView])

  const clampScale = (value: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))

  const adjustScale = useCallback((delta: number) => {
    setScale((prev) => clampScale(Number((prev + delta).toFixed(2))))
  }, [])

  useEffect(() => {
    if (!open) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        e.stopImmediatePropagation()
        close()
      }
    }

    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [open, close])

  useEffect(() => {
    if (!open) return

    const stage = stageRef.current
    if (!stage) return

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const delta = e.deltaY < 0 ? WHEEL_STEP : -WHEEL_STEP
      adjustScale(delta)
    }

    stage.addEventListener('wheel', onWheel, { passive: false })
    return () => stage.removeEventListener('wheel', onWheel)
  }, [open, adjustScale])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (scale <= MIN_SCALE) return
    draggingRef.current = true
    movedRef.current = false
    dragStartRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return
    const dx = e.clientX - dragStartRef.current.x
    const dy = e.clientY - dragStartRef.current.y
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) movedRef.current = true
    setPan({
      x: dragStartRef.current.panX + dx,
      y: dragStartRef.current.panY + dy,
    })
  }

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    e.currentTarget.releasePointerCapture(e.pointerId)
  }

  const onStageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation()
    if (movedRef.current) {
      movedRef.current = false
      return
    }
    if (scale <= MIN_SCALE) close()
  }

  const overlay = open
    ? createPortal(
        <div
          className="photo-lightbox-backdrop"
          onClick={close}
          role="dialog"
          aria-modal="true"
          aria-label="Полноэкранный просмотр фотографии"
        >
          <div className="photo-lightbox-toolbar" onClick={(e) => e.stopPropagation()}>
            <div className="photo-lightbox-zoom-controls">
              <button
                type="button"
                className="btn small"
                aria-label="Уменьшить"
                onClick={() => adjustScale(-BUTTON_STEP)}
              >
                −
              </button>
              <span className="photo-lightbox-scale">{Math.round(scale * 100)}%</span>
              <button
                type="button"
                className="btn small"
                aria-label="Увеличить"
                onClick={() => adjustScale(BUTTON_STEP)}
              >
                +
              </button>
              <button type="button" className="btn small" onClick={resetView}>
                Сброс
              </button>
            </div>
            <button type="button" className="btn ghost small" onClick={close}>
              Закрыть
            </button>
          </div>
          <div
            ref={stageRef}
            className={`photo-lightbox-stage${scale <= MIN_SCALE ? ' photo-lightbox-stage--fit' : ''}`}
            onClick={onStageClick}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <button
              type="button"
              className="photo-lightbox-close-float"
              aria-label="Закрыть"
              onClick={(e) => {
                e.stopPropagation()
                close()
              }}
            >
              ×
            </button>
            <img
              src={src}
              alt={alt}
              className="photo-lightbox-image"
              style={{
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
              }}
              draggable={false}
            />
          </div>
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <img
        src={src}
        alt={alt}
        className={className}
        onError={onError}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen(true)
          }
        }}
        role="button"
        tabIndex={0}
        title="Открыть на весь экран"
        aria-label={`${alt}. Открыть на весь экран`}
      />
      {overlay}
    </>
  )
}
