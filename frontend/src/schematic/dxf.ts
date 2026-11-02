/**
 * Minimal DXF writer (AutoCAD R12, ASCII) for the circuit schematic: every CAD program reads
 * R12 — AutoCAD, LibreCAD, QCAD, DraftSight. Pure functions, no dependency.
 *
 * Geometry comes in screen pixels (y down) and leaves in millimetres (y up), 1 px = 0.25 mm.
 * Layers: COMPONENTS (outlines), TERMINALS (pin circles), WIRES, TEXT.
 * Text is ASCII only (see dxfText).
 */
export interface GeoBox {
  label: string
  sub: string
  x: number
  y: number
  w: number
  h: number
}
export interface GeoPin {
  name: string
  x: number
  y: number
}
export interface Geometry {
  boxes: GeoBox[]
  pins: GeoPin[]
  wires: [number, number][][]
}

export const MM_PER_PX = 0.25
const LAYERS: [string, number][] = [
  ['COMPONENTS', 7],
  ['TERMINALS', 1],
  ['WIRES', 5],
  ['TEXT', 3],
  ['FRAME', 7],
]

/**
 * Drawing sheet: an ISO 5457 frame (20 mm binding margin on the left, 10 mm elsewhere) on the
 * smallest ISO A sheet, landscape, that holds the schematic at 1:1 (mm), with an ISO 7200-style
 * title block (180 mm wide) in the bottom-right corner. Fields are ASCII (see dxfText); a
 * non-ASCII value (a Hebrew project name) is replaced by `fallback` rather than by '?'s.
 */
export interface TitleBlock {
  title: string
  drawing: string
  project: string
  fallback?: string
  date: string
  rows?: [string, string][]
}

const SHEETS: [string, number, number][] = [
  ['A4', 297, 210],
  ['A3', 420, 297],
  ['A2', 594, 420],
  ['A1', 841, 594],
  ['A0', 1189, 841],
]
const TB_W = 180
const TB_ROW = 7

export function pickSheet(wMm: number, hMm: number, rows: number): { name: string; w: number; h: number } {
  const tbH = TB_ROW * (rows + 4)
  for (const [name, w, h] of SHEETS) {
    if (wMm + 20 + 10 + 20 <= w && hMm + 20 + tbH + 20 <= h) return { name, w, h }
  }
  const [name, w, h] = SHEETS[SHEETS.length - 1]!
  return { name: `${name} (drawing larger than the sheet)`, w, h }
}
const ASCII: Record<string, string> = { 'Ω': 'Ohm', 'µ': 'u', '°': '%%d', '·': '.', '–': '-', '—': '-' }

/**
 * R12 TEXT is single-byte, and the \U+XXXX escape is not understood by every reader (ezdxf's
 * renderer prints it literally), so the drawing carries ASCII only: component ids, types and
 * terminal names — the engineering references. Hebrew labels stay in the app.
 */
export function dxfText(s: string): string {
  return [...s].map((c) => ((c.codePointAt(0) ?? 63) < 128 ? c : (ASCII[c] ?? '?'))).join('')
}

const num = (v: number) => (Math.abs(v) < 1e-9 ? '0' : v.toFixed(3))

export function toDxf(g: Geometry, sheet?: TitleBlock): string {
  const out: string[] = []
  const pair = (code: number, value: string | number) => out.push(String(code), String(value))
  const X = (x: number) => num(x * MM_PER_PX)
  const Y = (y: number) => num(-y * MM_PER_PX)
  const line = (layer: string, a: [number, number], b: [number, number]) => {
    pair(0, 'LINE')
    pair(8, layer)
    pair(10, X(a[0]))
    pair(20, Y(a[1]))
    pair(30, 0)
    pair(11, X(b[0]))
    pair(21, Y(b[1]))
    pair(31, 0)
  }
  const text = (s: string, x: number, y: number, h: number, centre = true) => {
    pair(0, 'TEXT')
    pair(8, 'TEXT')
    pair(10, X(x))
    pair(20, Y(y))
    pair(30, 0)
    pair(40, num(h))
    pair(1, dxfText(s))
    if (centre) {
      pair(72, 1) // horizontal: centre
      pair(11, X(x))
      pair(21, Y(y))
      pair(31, 0)
    }
  }

  pair(0, 'SECTION')
  pair(2, 'HEADER')
  pair(9, '$ACADVER')
  pair(1, 'AC1009')
  pair(9, '$DWGCODEPAGE')
  pair(3, 'ANSI_1252')
  pair(0, 'ENDSEC')

  pair(0, 'SECTION')
  pair(2, 'TABLES')
  pair(0, 'TABLE')
  pair(2, 'LAYER')
  pair(70, LAYERS.length)
  for (const [name, colour] of LAYERS) {
    pair(0, 'LAYER')
    pair(2, name)
    pair(70, 0)
    pair(62, colour)
    pair(6, 'CONTINUOUS')
  }
  pair(0, 'ENDTAB')
  pair(0, 'ENDSEC')

  pair(0, 'SECTION')
  pair(2, 'ENTITIES')
  for (const b of g.boxes) {
    const c: [number, number][] = [
      [b.x, b.y],
      [b.x + b.w, b.y],
      [b.x + b.w, b.y + b.h],
      [b.x, b.y + b.h],
    ]
    c.forEach((p, i) => line('COMPONENTS', p, c[(i + 1) % 4]!))
    text(b.label, b.x + b.w / 2, b.y + b.h / 2 - 2, 3.5)
    if (b.sub) text(b.sub, b.x + b.w / 2, b.y + b.h / 2 + 18, 2.5)
  }
  for (const p of g.pins) {
    pair(0, 'CIRCLE')
    pair(8, 'TERMINALS')
    pair(10, X(p.x))
    pair(20, Y(p.y))
    pair(30, 0)
    pair(40, num(0.8))
    text(p.name, p.x + 4, p.y - 4, 1.8, false)
  }
  for (const w of g.wires) {
    for (let i = 1; i < w.length; i++) line('WIRES', w[i - 1]!, w[i]!)
  }
  for (const [x, y] of junctions(g)) {
    pair(0, 'CIRCLE')
    pair(8, 'WIRES')
    pair(10, X(x))
    pair(20, Y(y))
    pair(30, 0)
    pair(40, num(0.5))
  }
  if (sheet) frame(g, sheet, line, text)
  pair(0, 'ENDSEC')
  pair(0, 'EOF')
  return out.join('\r\n') + '\r\n'
}

type LineFn = (layer: string, a: [number, number], b: [number, number]) => void
type TextFn = (s: string, x: number, y: number, h: number, centre?: boolean) => void

/** Frame and title block, in the geometry's pixel space (the writers convert to mm). */
function frame(g: Geometry, tb: TitleBlock, line: LineFn, text: TextFn): void {
  const xs = [...g.boxes.flatMap((b) => [b.x, b.x + b.w]), ...g.pins.map((p) => p.x), ...g.wires.flat().map((p) => p[0])]
  const ys = [...g.boxes.flatMap((b) => [b.y, b.y + b.h]), ...g.pins.map((p) => p.y), ...g.wires.flat().map((p) => p[1])]
  if (!xs.length) return
  const k = 1 / MM_PER_PX // mm → px
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const rows: [string, string][] = [
    ['TITLE', ascii(tb.title, tb.fallback)],
    ['DRAWING', ascii(tb.drawing, tb.fallback)],
    ['PROJECT', ascii(tb.project, tb.fallback)],
    ['DATE', tb.date],
    ...(tb.rows ?? []).map(([a, b]): [string, string] => [ascii(a), ascii(b)]),
  ]
  const sh = pickSheet((x1 - x0) * MM_PER_PX, (y1 - y0) * MM_PER_PX, rows.length)
  rows.push(['SCALE / SHEET', `1:1  ${sh.name}`], ['DRAWN BY', ''], ['CHECKED', ''])
  // sheet in px: drawing centred in the area above the title block
  const W = sh.w * k
  const H = sh.h * k
  const tbH = TB_ROW * rows.length * k
  const left = x0 - (W - 30 * k - (x1 - x0)) / 2 - 20 * k
  const top = y0 - (H - 20 * k - tbH - (y1 - y0)) / 2 - 10 * k
  const rect = (ax: number, ay: number, bx: number, by: number) => {
    line('FRAME', [ax, ay], [bx, ay])
    line('FRAME', [bx, ay], [bx, by])
    line('FRAME', [bx, by], [ax, by])
    line('FRAME', [ax, by], [ax, ay])
  }
  rect(left, top, left + W, top + H) // trimmed sheet edge
  const fl = left + 20 * k
  const fr = left + W - 10 * k
  const ft = top + 10 * k
  const fb = top + H - 10 * k
  rect(fl, ft, fr, fb) // drawing frame
  const tl = fr - TB_W * k
  const tt = fb - tbH
  rect(tl, tt, fr, fb)
  rows.forEach(([key, value], i) => {
    const y = tt + i * TB_ROW * k
    if (i) line('FRAME', [tl, y], [fr, y])
    text(key, tl + 2 * k, y + 5 * k, 2.2, false)
    text(value, tl + 42 * k, y + 5 * k, 3, false)
  })
  line('FRAME', [tl + 40 * k, tt], [tl + 40 * k, fb])
}

function ascii(s: string, fallback = ''): string {
  return [...s].every((c) => (c.codePointAt(0) ?? 999) < 128 || c in ASCII) ? s : fallback
}

/**
 * Junction dots: wire end points where three or more conductors meet — several segment ends at
 * one point, or a wire ending on another wire's run (a T). Terminals are not junctions.
 */
export function junctions(g: Geometry, tol = 0.5): [number, number][] {
  const segs: [[number, number], [number, number]][] = []
  for (const w of g.wires) for (let i = 1; i < w.length; i++) segs.push([w[i - 1]!, w[i]!])
  const isPin = (p: [number, number]) => g.pins.some((q) => Math.hypot(q.x - p[0], q.y - p[1]) < tol)
  const out: [number, number][] = []
  const seen = new Set<string>()
  for (const w of g.wires) {
    for (const p of [w[0], w[w.length - 1]]) {
      if (!p || isPin(p)) continue
      let ends = 0
      let through = false
      for (const [a, b] of segs) {
        const atA = Math.hypot(a[0] - p[0], a[1] - p[1]) < tol
        const atB = Math.hypot(b[0] - p[0], b[1] - p[1]) < tol
        if (atA || atB) ends += 1
        else {
          // p strictly inside an axis-parallel segment
          const onV = Math.abs(a[0] - b[0]) < tol && Math.abs(a[0] - p[0]) < tol && (p[1] - a[1]) * (p[1] - b[1]) < 0
          const onH = Math.abs(a[1] - b[1]) < tol && Math.abs(a[1] - p[1]) < tol && (p[0] - a[0]) * (p[0] - b[0]) < 0
          if (onV || onH) through = true
        }
      }
      const k = `${p[0].toFixed(1)},${p[1].toFixed(1)}`
      if ((ends >= 3 || through) && !seen.has(k)) {
        seen.add(k)
        out.push(p)
      }
    }
  }
  return out
}

/** Corner points of an SVG path made of M/L (and Q, whose end point is kept). */
export function pathPoints(d: string): [number, number][] {
  const nums = d.match(/-?\d*\.?\d+(?:e-?\d+)?/gi)?.map(Number) ?? []
  const cmds = d.match(/[MLQ]/gi) ?? []
  const pts: [number, number][] = []
  let k = 0
  for (const c of cmds) {
    if (c.toUpperCase() === 'Q') k += 2 // control point
    const x = nums[k]
    const y = nums[k + 1]
    if (x === undefined || y === undefined) break
    pts.push([x, y])
    k += 2
  }
  return pts
}
