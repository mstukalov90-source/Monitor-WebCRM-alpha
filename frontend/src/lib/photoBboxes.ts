export interface PhotoBbox {
  x1: number
  y1: number
  x2: number
  y2: number
  normalized: boolean
  label?: string
  score?: number
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function pickNumber(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = asNumber(record[key])
    if (value != null) return value
  }
  return null
}

function pickLabel(record: Record<string, unknown>): string | undefined {
  for (const key of ['label', 'class', 'cls', 'class_name', 'name']) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return undefined
}

function pickScore(record: Record<string, unknown>): number | undefined {
  const value = pickNumber(record, ['score', 'confidence', 'conf', 'prob'])
  return value == null ? undefined : value
}

function coordsLookNormalized(values: number[]): boolean {
  return values.every((value) => value >= -0.05 && value <= 1.05)
}

function fromXyxy(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  extra?: { label?: string; score?: number },
): PhotoBbox | null {
  if (![x1, y1, x2, y2].every(Number.isFinite)) return null
  const left = Math.min(x1, x2)
  const top = Math.min(y1, y2)
  const right = Math.max(x1, x2)
  const bottom = Math.max(y1, y2)
  if (right <= left || bottom <= top) return null
  return {
    x1: left,
    y1: top,
    x2: right,
    y2: bottom,
    normalized: coordsLookNormalized([left, top, right, bottom]),
    label: extra?.label,
    score: extra?.score,
  }
}

function fromXywh(
  x: number,
  y: number,
  w: number,
  h: number,
  extra?: { label?: string; score?: number },
): PhotoBbox | null {
  if (w <= 0 || h <= 0) return null
  return fromXyxy(x, y, x + w, y + h, extra)
}

function parseCoordList(raw: unknown[], extra?: { label?: string; score?: number }): PhotoBbox | null {
  const nums = raw.map(asNumber)
  if (nums.length < 4 || nums.slice(0, 4).some((value) => value == null)) return null
  const [a, b, c, d] = nums as number[]
  return fromXyxy(a, b, c, d, extra)
}

function parseRecord(record: Record<string, unknown>): PhotoBbox | null {
  const extra = { label: pickLabel(record), score: pickScore(record) }
  const nested = record.bbox ?? record.box ?? record.xyxy
  if (Array.isArray(nested)) {
    const parsed = parseCoordList(nested, extra)
    if (parsed) return parsed
  }

  const x1 = pickNumber(record, ['x1', 'xmin', 'left', 'min_x'])
  const y1 = pickNumber(record, ['y1', 'ymin', 'top', 'min_y'])
  const x2 = pickNumber(record, ['x2', 'xmax', 'right', 'max_x'])
  const y2 = pickNumber(record, ['y2', 'ymax', 'bottom', 'max_y'])
  if (x1 != null && y1 != null && x2 != null && y2 != null) {
    return fromXyxy(x1, y1, x2, y2, extra)
  }

  const x = pickNumber(record, ['x', 'left'])
  const y = pickNumber(record, ['y', 'top'])
  const w = pickNumber(record, ['w', 'width'])
  const h = pickNumber(record, ['h', 'height'])
  if (x != null && y != null && w != null && h != null) {
    return fromXywh(x, y, w, h, extra)
  }
  return null
}

export function parsePhotoBboxes(raw: unknown): PhotoBbox[] {
  if (raw == null) return []
  let value: unknown = raw
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return []
    try {
      value = JSON.parse(text) as unknown
    } catch {
      return []
    }
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    const nested = record.bboxes ?? record.boxes ?? record.detections
    if (Array.isArray(nested)) value = nested
    else return []
  }
  if (!Array.isArray(value)) return []
  const boxes: PhotoBbox[] = []
  for (const item of value) {
    if (Array.isArray(item)) {
      const parsed = parseCoordList(item)
      if (parsed) boxes.push(parsed)
      continue
    }
    if (item && typeof item === 'object') {
      const parsed = parseRecord(item as Record<string, unknown>)
      if (parsed) boxes.push(parsed)
    }
  }
  return boxes
}

export function bboxCaption(box: PhotoBbox): string | null {
  const parts: string[] = []
  if (box.label) parts.push(box.label)
  if (box.score != null) parts.push(box.score.toFixed(2))
  return parts.length ? parts.join(' ') : null
}
