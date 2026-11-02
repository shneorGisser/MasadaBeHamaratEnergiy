/**
 * The circuit as a figure for the report: the same geometry as the DXF (component outlines,
 * every terminal, the routed cables, junction dots), drawn as a print-ready SVG and rasterised
 * to PNG for Word and HTML.
 *
 * Why not a screenshot of the editor: the editor draws handles, selection, live currents and
 * the grid, at whatever zoom the student left it. A report figure needs the wiring only, at a
 * fixed scale, black on white, and must be the circuit of the run that is reported (the run's
 * own snapshot), not whatever is on the bench now.
 */
import { junctions, type Geometry } from './dxf'
import type { CircuitModel, ComponentType } from './model'
import { circuitGeometry } from './useDxfExport'

const PAD = 28
const FONT = "David, 'David Libre', 'Noto Sans Hebrew', Arial, sans-serif"

const LABEL = 10

/** Greedy word wrap to `max` characters a line and at most `maxLines` lines; what does not fit
 * is dropped by whole words and marked with an ellipsis (never cut inside a word or a formula). */
export function wrap(text: string, max: number, maxLines = 3): string[] {
  const lines: string[] = []
  let cur = ''
  for (const word of text.split(/\s+/).filter(Boolean)) {
    if (cur && (cur + ' ' + word).length > max) {
      lines.push(cur)
      cur = word
    } else cur = cur ? `${cur} ${word}` : word
  }
  if (cur) lines.push(cur)
  if (lines.length <= maxLines) return lines
  const kept = lines.slice(0, Math.max(1, maxLines))
  kept[kept.length - 1] += '…'
  return kept
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export interface Diagram {
  svg: string
  width: number
  height: number
}

/** Which edge of its outline a pin sits on, so its name can be written inside the box. */
type Edge = 'left' | 'right' | 'top' | 'bottom'
function edgeOf(p: { x: number; y: number }, g: Geometry): Edge | null {
  let best: [Edge, number] | null = null
  for (const b of g.boxes) {
    if (p.x < b.x - 2 || p.x > b.x + b.w + 2 || p.y < b.y - 2 || p.y > b.y + b.h + 2) continue
    const d: [Edge, number][] = [
      ['left', Math.abs(p.x - b.x)],
      ['right', Math.abs(p.x - b.x - b.w)],
      ['top', Math.abs(p.y - b.y)],
      ['bottom', Math.abs(p.y - b.y - b.h)],
    ]
    for (const c of d) if (!best || c[1] < best[1]) best = c
  }
  return best && best[1] < 3 ? best[0] : null
}

export function diagramSvg(g: Geometry, labels: Record<string, string> = {}): Diagram {
  const xs: number[] = []
  const ys: number[] = []
  for (const b of g.boxes) {
    xs.push(b.x, b.x + b.w)
    ys.push(b.y, b.y + b.h)
  }
  for (const w of g.wires)
    for (const [x, y] of w) {
      xs.push(x)
      ys.push(y)
    }
  if (!xs.length) {
    xs.push(0, 100)
    ys.push(0, 100)
  }
  const x0 = Math.min(...xs) - PAD
  const y0 = Math.min(...ys) - PAD
  const width = Math.ceil(Math.max(...xs) + PAD - x0)
  const height = Math.ceil(Math.max(...ys) + PAD - y0)
  const out: string[] = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${x0} ${y0} ${width} ${height}" font-family="${esc(FONT)}">`,
    `<rect x="${x0}" y="${y0}" width="${width}" height="${height}" fill="#ffffff"/>`,
  ]
  // outlines and their names: the id, and the Hebrew name wrapped to the room between the
  // pin labels (estimated width; the figure is rendered by the student's browser)
  for (const b of g.boxes) {
    out.push(`<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="4" fill="#f6f7f8" stroke="#1d2125" stroke-width="1.3"/>`)
    const cx = b.x + b.w / 2
    const he = labels[b.label]
    const lines = he ? wrap(he, Math.max(8, Math.floor((b.w - 60) / (LABEL * 0.55))), Math.max(1, Math.floor((b.h - 34) / (LABEL + 2)))) : []
    const block = 15 + lines.length * (LABEL + 2)
    let y = b.y + b.h / 2 - block / 2 + 12
    out.push(`<text x="${cx}" y="${y}" text-anchor="middle" font-size="15" font-weight="700" fill="#1d2125">${esc(b.label)}</text>`)
    for (const line of lines) {
      y += LABEL + 2
      out.push(`<text x="${cx}" y="${y}" text-anchor="middle" font-size="${LABEL}" fill="#4a5056" direction="rtl" unicode-bidi="embed">${esc(line)}</text>`)
    }
  }
  // cables over the outlines' edges, under the pins
  for (const w of g.wires) {
    if (w.length < 2) continue
    const pts = w.map(([x, y]) => `${x},${y}`).join(' ')
    out.push(`<polyline points="${pts}" fill="none" stroke="#14365f" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>`)
  }
  for (const [x, y] of junctions(g)) out.push(`<circle cx="${x}" cy="${y}" r="3.2" fill="#14365f"/>`)
  for (const p of g.pins) {
    out.push(`<circle cx="${p.x}" cy="${p.y}" r="2.6" fill="#ffffff" stroke="#1d2125" stroke-width="1.1"/>`)
    const e = edgeOf(p, g)
    const [tx, ty, anchor] =
      e === 'left'
        ? [p.x + 5, p.y + 3.5, 'start']
        : e === 'right'
          ? [p.x - 5, p.y + 3.5, 'end']
          : e === 'top'
            ? [p.x, p.y + 12, 'middle']
            : e === 'bottom'
              ? [p.x, p.y - 5, 'middle']
              : [p.x + 5, p.y - 4, 'start']
    out.push(`<text x="${tx}" y="${ty}" text-anchor="${anchor}" font-size="9" fill="#33393f">${esc(p.name)}</text>`)
  }
  out.push('</svg>')
  return { svg: out.join(''), width, height }
}

export function circuitDiagram(c: CircuitModel, catalog: ComponentType[]): Diagram {
  const byType = new Map(catalog.map((t) => [t.type, t.label_he]))
  const labels: Record<string, string> = {}
  for (const comp of c.components) labels[comp.id] = byType.get(comp.type) ?? comp.type
  return diagramSvg(circuitGeometry(c, catalog), labels)
}

/** PNG (base64, no data: prefix) at `scale`× for print, capped at 3000 px on the long side. */
export async function diagramPng(d: Diagram, scale = 2.5): Promise<string> {
  const k = Math.min(scale, 3000 / Math.max(d.width, d.height))
  const url = URL.createObjectURL(new Blob([d.svg], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    img.decoding = 'sync'
    await new Promise<void>((ok, fail) => {
      img.onload = () => ok()
      img.onerror = () => fail(new Error('circuit diagram did not render'))
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(d.width * k)
    canvas.height = Math.round(d.height * k)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('no canvas')
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png').split(',')[1] ?? ''
  } finally {
    URL.revokeObjectURL(url)
  }
}
