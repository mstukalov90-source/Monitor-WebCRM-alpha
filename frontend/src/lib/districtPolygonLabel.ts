import L from 'leaflet'

const SVG_NS = 'http://www.w3.org/2000/svg'
const LABEL_CLASS = 'district-hood-label'
const MIN_FONT_PX = 7
const MAX_FONT_PX = 12
const LINE_HEIGHT = 1.15
const EDGE_PAD_PX = 3
const MIN_POLY_PX = 16

export type DistrictLabelFit = {
  fontSize: number
  lines: string[]
}

export type DistrictLabelPlacement = DistrictLabelFit & {
  x: number
  y: number
  angle: number
}

type PathWithHoodLabel = L.Path & {
  _path?: SVGPathElement
  _hoodLabel?: HoodLabelBinding
  _hoodAttach?: () => void
}

type HoodLabelBinding = {
  groupEl: SVGGElement
  textEl: SVGTextElement
  onUpdate: () => void
  map: L.Map
}

type Pt = { x: number; y: number }

let measureCtx: CanvasRenderingContext2D | null | undefined

function getMeasureCtx(): CanvasRenderingContext2D | null {
  if (measureCtx !== undefined) return measureCtx
  const canvas = document.createElement('canvas')
  measureCtx = canvas.getContext('2d')
  return measureCtx
}

function measureAt(fontSize: number): (s: string) => number {
  const ctx = getMeasureCtx()
  return (s: string) => {
    if (!ctx) return s.length * fontSize * 0.55
    ctx.font = `600 ${fontSize}px sans-serif`
    return ctx.measureText(s).width
  }
}

function tokenizeDistrictLabel(text: string): string[] {
  return text
    .trim()
    .split(/(?<=-)| +/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function joinLabelTokens(left: string, right: string): string {
  if (left.endsWith('-')) return `${left}${right}`
  return `${left} ${right}`
}

export function wrapDistrictLabel(
  text: string,
  measure: (s: string) => number,
  maxWidth: number,
): string[] {
  const tokens = tokenizeDistrictLabel(text)
  if (!tokens.length) return []
  if (maxWidth <= 0) {
    return [tokens.reduce((acc, token) => (acc ? joinLabelTokens(acc, token) : token), '')]
  }

  const lines: string[] = []
  let current = ''
  for (const token of tokens) {
    const next = current ? joinLabelTokens(current, token) : token
    if (current && measure(next) > maxWidth) {
      lines.push(current)
      current = token
    } else {
      current = next
    }
  }
  if (current) lines.push(current)
  return lines
}

/** All ways to break the name on spaces and hyphens, fewer lines first. */
export function wrapLayoutsForLabel(text: string): string[][] {
  const tokens = tokenizeDistrictLabel(text)
  if (!tokens.length) return []
  if (tokens.length === 1) return [[tokens[0] ?? '']]

  const n = tokens.length
  const layouts: string[][] = []
  const maxMask = 1 << (n - 1)
  for (let mask = 0; mask < maxMask; mask += 1) {
    const lines: string[] = []
    let current = tokens[0] ?? ''
    for (let i = 0; i < n - 1; i += 1) {
      const nextToken = tokens[i + 1] ?? ''
      if (mask & (1 << i)) {
        lines.push(current)
        current = nextToken
      } else {
        current = joinLabelTokens(current, nextToken)
      }
    }
    lines.push(current)
    layouts.push(lines)
  }
  layouts.sort((a, b) => a.length - b.length || a.join('\n').length - b.join('\n').length)
  return layouts
}

export function pathBoundsArea(path: L.Path): number {
  const bounds = (path as L.Polyline).getBounds()
  if (!bounds.isValid()) return 0
  return (bounds.getEast() - bounds.getWest()) * (bounds.getNorth() - bounds.getSouth())
}

export function largestDistrictPath(paths: L.Path[]): L.Path | null {
  let best: L.Path | null = null
  let bestArea = -1
  for (const path of paths) {
    const area = pathBoundsArea(path)
    if (area > bestArea) {
      best = path
      bestArea = area
    }
  }
  return best
}

function svgPathOf(path: L.Path): SVGPathElement | undefined {
  return (path as PathWithHoodLabel)._path
}

function makeHitTest(d: string): ((x: number, y: number) => boolean) | null {
  if (!d || typeof Path2D === 'undefined') return null
  const ctx = getMeasureCtx()
  if (!ctx) return null
  const path2d = new Path2D(d)
  return (x, y) => ctx.isPointInPath(path2d, x, y, 'evenodd')
}

function readableAngle(deg: number): number {
  let a = deg % 180
  if (a > 90) a -= 180
  if (a < -90) a += 180
  return a
}

function principalAngle(el: SVGPathElement): number {
  const n = 36
  let len = 0
  try {
    len = el.getTotalLength()
  } catch {
    return 0
  }
  if (len <= 0) return 0

  const pts: Pt[] = []
  let mx = 0
  let my = 0
  for (let i = 0; i < n; i += 1) {
    const p = el.getPointAtLength((i / n) * len)
    pts.push({ x: p.x, y: p.y })
    mx += p.x
    my += p.y
  }
  mx /= n
  my /= n
  let xx = 0
  let yy = 0
  let xy = 0
  for (const p of pts) {
    const dx = p.x - mx
    const dy = p.y - my
    xx += dx * dx
    yy += dy * dy
    xy += dx * dy
  }
  return readableAngle((Math.atan2(2 * xy, xx - yy) / 2) * (180 / Math.PI))
}

function clearance(el: SVGPathElement, hit: (x: number, y: number) => boolean, x: number, y: number): number {
  if (!hit(x, y)) return -1
  let len = 0
  try {
    len = el.getTotalLength()
  } catch {
    return 0
  }
  if (len <= 0) return 0
  let min = Infinity
  const samples = 20
  for (let i = 0; i < samples; i += 1) {
    const p = el.getPointAtLength((i / samples) * len)
    const d = Math.hypot(p.x - x, p.y - y)
    if (d < min) min = d
  }
  return min
}

function visualCenter(el: SVGPathElement, hit: (x: number, y: number) => boolean, bbox: DOMRect): Pt {
  const steps = 7
  let best: Pt & { score: number } = {
    x: bbox.x + bbox.width / 2,
    y: bbox.y + bbox.height / 2,
    score: clearance(el, hit, bbox.x + bbox.width / 2, bbox.y + bbox.height / 2),
  }
  for (let iy = 1; iy < steps; iy += 1) {
    for (let ix = 1; ix < steps; ix += 1) {
      const x = bbox.x + (ix / steps) * bbox.width
      const y = bbox.y + (iy / steps) * bbox.height
      const score = clearance(el, hit, x, y)
      if (score > best.score) best = { x, y, score }
    }
  }
  return best
}

function candidatePositions(el: SVGPathElement, hit: (x: number, y: number) => boolean, bbox: DOMRect): Pt[] {
  const center = visualCenter(el, hit, bbox)
  const pts: Pt[] = [center]
  const stepX = bbox.width * 0.18
  const stepY = bbox.height * 0.18
  const dirs = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
    [1, 1],
    [1, -1],
    [-1, 1],
    [-1, -1],
    [2, 0],
    [-2, 0],
    [0, 2],
    [0, -2],
  ]
  for (const [dx, dy] of dirs) {
    const x = center.x + dx * stepX
    const y = center.y + dy * stepY
    if (hit(x, y)) pts.push({ x, y })
  }
  return pts
}

function candidateAngles(axis: number): number[] {
  const raw = [0, axis, axis + 18, axis - 18, axis + 32, axis - 32, 90, -90]
  const seen = new Set<number>()
  const out: number[] = []
  for (const value of raw) {
    const a = Math.round(readableAngle(value) * 10) / 10
    if (seen.has(a)) continue
    seen.add(a)
    out.push(a)
  }
  out.sort((a, b) => Math.abs(a) - Math.abs(b))
  return out
}

function rotatedRectInside(
  cx: number,
  cy: number,
  width: number,
  height: number,
  angleDeg: number,
  hit: (x: number, y: number) => boolean,
): boolean {
  const rad = (angleDeg * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const hw = width / 2 + EDGE_PAD_PX
  const hh = height / 2 + EDGE_PAD_PX
  const nx = 4
  const ny = 3
  for (let iy = 0; iy <= ny; iy += 1) {
    for (let ix = 0; ix <= nx; ix += 1) {
      const lx = -hw + (2 * hw * ix) / nx
      const ly = -hh + (2 * hh * iy) / ny
      const x = cx + lx * cos - ly * sin
      const y = cy + lx * sin + ly * cos
      if (!hit(x, y)) return false
    }
  }
  return true
}

export function placeDistrictLabel(
  el: SVGPathElement,
  text: string,
): DistrictLabelPlacement | null {
  let bbox: DOMRect
  try {
    bbox = el.getBBox()
  } catch {
    return null
  }
  if (bbox.width < MIN_POLY_PX || bbox.height < MIN_POLY_PX) return null

  const d = el.getAttribute('d') ?? ''
  const hit = makeHitTest(d)
  if (!hit) return null

  const layouts = wrapLayoutsForLabel(text)
  if (!layouts.length) return null

  const positions = candidatePositions(el, hit, bbox)
  const angles = candidateAngles(principalAngle(el))

  for (let fontSize = MAX_FONT_PX; fontSize >= MIN_FONT_PX; fontSize -= 1) {
    const measure = measureAt(fontSize)
    let best: { placement: DistrictLabelPlacement; score: number } | null = null

    for (const lines of layouts) {
      const width = Math.max(...lines.map((line) => measure(line)), 0)
      const height = lines.length * fontSize * LINE_HEIGHT
      if (width <= 0 || height <= 0) continue

      for (const pos of positions) {
        for (const angle of angles) {
          if (!rotatedRectInside(pos.x, pos.y, width, height, angle, hit)) continue
          const score =
            -lines.length * 80 -
            Math.abs(angle) * 0.35 -
            Math.hypot(pos.x - positions[0]!.x, pos.y - positions[0]!.y) * 0.05
          if (!best || score > best.score) {
            best = {
              score,
              placement: { fontSize, lines, x: pos.x, y: pos.y, angle },
            }
          }
        }
      }
    }

    if (best) return best.placement
  }

  return null
}

function applyPlacement(textEl: SVGTextElement, placement: DistrictLabelPlacement): void {
  const { fontSize, lines, x, y, angle } = placement
  const lineHeight = fontSize * LINE_HEIGHT
  const blockH = lines.length * lineHeight
  const startY = y - blockH / 2 + fontSize * 0.85

  textEl.setAttribute('font-size', String(fontSize))
  textEl.setAttribute('transform', `rotate(${angle} ${x} ${y})`)
  while (textEl.firstChild) {
    textEl.removeChild(textEl.firstChild)
  }
  for (let i = 0; i < lines.length; i += 1) {
    const tspan = document.createElementNS(SVG_NS, 'tspan')
    tspan.setAttribute('x', String(x))
    tspan.setAttribute('y', String(startY + i * lineHeight))
    tspan.textContent = lines[i] ?? ''
    textEl.appendChild(tspan)
  }
}

function syncHoodLabel(path: L.Path, text: string, binding: HoodLabelBinding): void {
  const el = svgPathOf(path)
  if (!el) return

  const placement = placeDistrictLabel(el, text)
  if (!placement) {
    binding.groupEl.setAttribute('display', 'none')
    binding.textEl.removeAttribute('transform')
    while (binding.textEl.firstChild) {
      binding.textEl.removeChild(binding.textEl.firstChild)
    }
    return
  }

  binding.groupEl.removeAttribute('display')
  applyPlacement(binding.textEl, placement)
}

export function bindDistrictPolygonLabel(path: L.Path, map: L.Map, text: string): void {
  unbindDistrictPolygonLabel(path)

  const typed = path as PathWithHoodLabel
  const attach = () => {
    if (typed._hoodLabel) return

    const el = svgPathOf(path)
    const parent = el?.parentNode
    if (!el || !parent) return

    const groupEl = document.createElementNS(SVG_NS, 'g')
    groupEl.setAttribute('class', `${LABEL_CLASS}-wrap`)
    groupEl.style.pointerEvents = 'none'

    const textEl = document.createElementNS(SVG_NS, 'text')
    textEl.setAttribute('class', LABEL_CLASS)
    textEl.setAttribute('fill', '#000')
    textEl.setAttribute('stroke', '#fff')
    textEl.setAttribute('stroke-width', '2.5')
    textEl.setAttribute('paint-order', 'stroke')
    textEl.setAttribute('text-anchor', 'middle')
    textEl.setAttribute('font-weight', '600')
    textEl.style.pointerEvents = 'none'
    groupEl.appendChild(textEl)
    parent.appendChild(groupEl)

    const onUpdate = () => {
      const binding = typed._hoodLabel
      if (!binding) return
      syncHoodLabel(path, text, binding)
    }
    typed._hoodLabel = { groupEl, textEl, onUpdate, map }
    map.on('zoomend viewreset moveend', onUpdate)
    onUpdate()
  }

  typed._hoodAttach = attach
  attach()
  if (!typed._hoodLabel) {
    path.once('add', attach)
    requestAnimationFrame(attach)
  } else {
    requestAnimationFrame(() => typed._hoodLabel?.onUpdate())
  }
}

export function unbindDistrictPolygonLabel(path: L.Path): void {
  const typed = path as PathWithHoodLabel
  if (typed._hoodAttach) {
    path.off('add', typed._hoodAttach)
    delete typed._hoodAttach
  }
  const binding = typed._hoodLabel
  if (!binding) return
  binding.map.off('zoomend viewreset moveend', binding.onUpdate)
  binding.groupEl.remove()
  delete typed._hoodLabel
}
