import { bboxCaption, type PhotoBbox } from '../lib/photoBboxes'

interface PhotoBboxOverlayProps {
  boxes: PhotoBbox[]
  naturalWidth: number
  naturalHeight: number
}

function toPixels(box: PhotoBbox, width: number, height: number) {
  if (box.normalized) {
    return {
      x1: box.x1 * width,
      y1: box.y1 * height,
      x2: box.x2 * width,
      y2: box.y2 * height,
    }
  }
  return { x1: box.x1, y1: box.y1, x2: box.x2, y2: box.y2 }
}

export function PhotoBboxOverlay({ boxes, naturalWidth, naturalHeight }: PhotoBboxOverlayProps) {
  if (!boxes.length || naturalWidth <= 0 || naturalHeight <= 0) return null

  const fontSize = Math.max(14, Math.round(Math.min(naturalWidth, naturalHeight) * 0.018))

  return (
    <svg
      className="photo-bbox-overlay"
      viewBox={`0 0 ${naturalWidth} ${naturalHeight}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {boxes.map((box, index) => {
        const px = toPixels(box, naturalWidth, naturalHeight)
        const width = px.x2 - px.x1
        const height = px.y2 - px.y1
        const caption = bboxCaption(box)
        const labelY = Math.max(fontSize + 2, px.y1 - 4)
        return (
          <g key={`${index}-${px.x1}-${px.y1}`}>
            <rect
              x={px.x1}
              y={px.y1}
              width={width}
              height={height}
              className="photo-bbox-rect"
            />
            {caption && (
              <text x={px.x1 + 2} y={labelY} className="photo-bbox-label" fontSize={fontSize}>
                {caption}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
