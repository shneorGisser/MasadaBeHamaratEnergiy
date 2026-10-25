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
        legend: { live: false },
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
          ...series.map((s) => ({
            label: s.label,
            stroke: s.color ?? COLORS[s.kind],
            width: s.kind === 'meas' ? 0 : 2,
            spanGaps: true,
            dash: s.kind === 'theory' ? [6, 4] : undefined,
            points: { show: true, size: s.kind === 'meas' ? 8 : 5, fill: s.color ?? COLORS[s.kind] },
          })),
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

  return <div ref={ref} dir="ltr" className="chart" data-testid={`chart-${title}`} />
}
