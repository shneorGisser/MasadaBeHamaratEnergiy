import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export interface Series {
  label: string
  kind: 'sim' | 'meas' | 'theory'
  points: [number, number][]
  /** overrides the colour of the kind (grouped series); dash and marker still follow the kind */
  color?: string
}

const COLORS: Record<Series['kind'], string> = { sim: '#1f6fb2', meas: '#a2462e', theory: '#4b6b2f' }

/**
 * Dual encoding (colour is not the only cue — colour-blind readers, grey-scale prints):
 * simulation = solid line, theory = dashed line, measurement = hollow markers with no line,
 * and each measured series of a chart gets its own marker shape.
 */
type Shape = 'circle' | 'triangle' | 'square' | 'diamond'
const SHAPES: Shape[] = ['circle', 'triangle', 'square', 'diamond']

function shapePath(shape: Shape, cx: number, cy: number, r: number, p: Path2D): void {
  switch (shape) {
    case 'circle':
      p.moveTo(cx + r, cy)
      p.arc(cx, cy, r, 0, 2 * Math.PI)
      break
    case 'triangle':
      p.moveTo(cx, cy - r * 1.15)
      p.lineTo(cx + r * 1.05, cy + r * 0.75)
      p.lineTo(cx - r * 1.05, cy + r * 0.75)
      p.closePath()
      break
    case 'square':
      p.rect(cx - r * 0.85, cy - r * 0.85, r * 1.7, r * 1.7)
      break
    case 'diamond':
      p.moveTo(cx, cy - r * 1.2)
      p.lineTo(cx + r * 1.2, cy)
      p.lineTo(cx, cy + r * 1.2)
      p.lineTo(cx - r * 1.2, cy)
      p.closePath()
      break
  }
}

function seriesShape(series: Series[], s: Series): Shape {
  return SHAPES[series.filter((x) => x.kind === 'meas').indexOf(s) % SHAPES.length]!
}

/** The legend swatch: the same line style or marker the plot uses. */
function Swatch({ s, shape }: { s: Series; shape: Shape }) {
  const color = s.color ?? COLORS[s.kind]
  if (s.kind === 'meas') {
    const d = {
      circle: <circle cx={14} cy={7} r={4.5} />,
      triangle: <polygon points="14,1.8 19,10.5 9,10.5" />,
      square: <rect x={10} y={3} width={8} height={8} />,
      diamond: <polygon points="14,1.5 19.5,7 14,12.5 8.5,7" />,
    }[shape]
    return (
      <svg width={28} height={14} aria-hidden fill="#fff" stroke={color} strokeWidth={2}>
        {d}
      </svg>
    )
  }
  return (
    <svg width={28} height={14} aria-hidden>
      <line x1={2} y1={7} x2={26} y2={7} stroke={color} strokeWidth={2.5} strokeDasharray={s.kind === 'theory' ? '6 4' : undefined} />
    </svg>
  )
}

/** uPlot points renderer drawing `shape` markers (hollow: the fill is the plot background). */
function shapePoints(shape: Shape) {
  return (u: uPlot, si: number, i0: number, i1: number) => {
    const xs = u.data[0] as (number | null)[]
    const ys = u.data[si] as (number | null)[]
    const r = 4.5 * devicePixelRatio
    const path = new Path2D()
    for (let i = i0; i <= i1; i++) {
      const x = xs[i]
      const y = ys[i]
      if (x == null || y == null) continue
      const px = u.valToPos(x, 'x', true)
      const py = u.valToPos(y, 'y', true)
      if (!Number.isFinite(px) || !Number.isFinite(py)) continue
      shapePath(shape, px, py, r, path)
    }
    return { stroke: path, fill: path }
  }
}

/**
 * XY scatter/line chart. Each series keeps its own x values (simulation and measurement
 * points rarely coincide), so data is merged onto a shared sorted x grid with nulls.
 */
export default function Chart({
  title,
  xLabel,
  yLabel,
  series,
  height = 260,
  log = false,
  markers,
  onPick,
}: {
  title: string
  xLabel: string
  yLabel: string
  series: Series[]
  height?: number
  /** logarithmic x and y axes (time–current characteristics); non-positive points are dropped */
  log?: boolean
  /** vertical cursor lines at these x values (scope cursors A, B) */
  markers?: number[]
  /** click on the plot area → x value under the pointer */
  onPick?: (x: number) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const markersRef = useRef<number[]>(markers ?? [])
  const pickRef = useRef(onPick)
  useEffect(() => {
    pickRef.current = onPick
  }, [onPick])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const pts = (s: Series) => (log ? s.points.filter((p) => p[0] > 0 && p[1] > 0) : s.points)
    const xs = Array.from(new Set(series.flatMap((s) => pts(s).map((p) => p[0])))).sort((a, b) => a - b)
    const data: (number | null)[][] = [xs]
    for (const s of series) {
      const m = new Map(pts(s).map((p) => [p[0], p[1]]))
      data.push(xs.map((x) => (m.has(x) ? (m.get(x) as number) : null)))
    }
    const width = Math.max(280, el.clientWidth || 480)
    const plot = new uPlot(
      {
        title,
        width,
        height,
        scales: log ? { x: { time: false, distr: 3 }, y: { distr: 3 } } : { x: { time: false } },
        legend: { show: false }, // drawn below in React: line style and marker shape, not colour alone
        hooks: {
          draw: [
            (u: uPlot) => {
              const ctx = u.ctx
              const ms = markersRef.current
              ms.forEach((x, i) => {
                const px = u.valToPos(x, 'x', true)
                if (!Number.isFinite(px)) return
                ctx.save()
                ctx.strokeStyle = i === 0 ? '#b07a1f' : '#7a3e8f'
                ctx.lineWidth = 1.5 * devicePixelRatio
                ctx.setLineDash([5 * devicePixelRatio, 4 * devicePixelRatio])
                ctx.beginPath()
                ctx.moveTo(px, u.bbox.top)
                ctx.lineTo(px, u.bbox.top + u.bbox.height)
                ctx.stroke()
                ctx.fillStyle = ctx.strokeStyle
                ctx.font = `${12 * devicePixelRatio}px sans-serif`
                ctx.fillText(i === 0 ? 'A' : 'B', px + 4 * devicePixelRatio, u.bbox.top + 14 * devicePixelRatio)
                ctx.restore()
              })
            },
          ],
        },
        axes: [{ label: xLabel }, { label: yLabel }],
        series: [
          { label: xLabel },
          ...series.map((s) => {
            const color = s.color ?? COLORS[s.kind]
            if (s.kind === 'meas') {
              const shape = seriesShape(series, s)
              return {
                label: s.label,
                stroke: color,
                width: 2,
                spanGaps: false,
                paths: () => null, // markers only, no line
                points: { show: true, size: 10, width: 2, stroke: color, fill: '#ffffff', paths: shapePoints(shape) },
              }
            }
            return {
              label: s.label,
              stroke: color,
              width: 2,
              spanGaps: true,
              dash: s.kind === 'theory' ? [6, 4] : undefined,
              points: { show: true, size: 4, fill: color },
            }
          }),
        ],
      },
      data as uPlot.AlignedData,
      el,
    )
    plotRef.current = plot
    const click = (e: MouseEvent) => {
      if (!pickRef.current) return
      const x = plot.posToVal(e.offsetX, 'x')
      if (Number.isFinite(x)) pickRef.current(x)
    }
    plot.over.addEventListener('click', click)
    const ro = new ResizeObserver(() => plot.setSize({ width: Math.max(280, el.clientWidth), height }))
    ro.observe(el)
    return () => {
      ro.disconnect()
      plot.over.removeEventListener('click', click)
      plot.destroy()
      plotRef.current = null
    }
  }, [title, xLabel, yLabel, series, height, log])

  // cursors move without rebuilding the plot
  useEffect(() => {
    markersRef.current = markers ?? []
    plotRef.current?.redraw(false)
  }, [markers])

  return (
    <div className="chart-wrap">
      <div ref={ref} dir="ltr" className="chart" data-testid={`chart-${title}`} />
      <ul className="chart-legend" aria-label={`מקרא: ${title}`}>
        {series.map((s) => (
          <li key={s.label}>
            <Swatch s={s} shape={seriesShape(series, s)} />
            <span>{s.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
