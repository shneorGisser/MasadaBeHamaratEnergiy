import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export interface Series {
  label: string
  kind: 'sim' | 'meas' | 'theory'
  points: [number, number][]
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
}: {
  title: string
  xLabel: string
  yLabel: string
  series: Series[]
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const xs = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p[0])))).sort((a, b) => a - b)
    const data: (number | null)[][] = [xs]
    for (const s of series) {
      const m = new Map(s.points.map((p) => [p[0], p[1]]))
      data.push(xs.map((x) => (m.has(x) ? (m.get(x) as number) : null)))
    }
    const width = Math.max(280, el.clientWidth || 480)
    const plot = new uPlot(
      {
        title,
        width,
        height,
        scales: { x: { time: false } },
        legend: { live: false },
        axes: [{ label: xLabel }, { label: yLabel }],
        series: [
          { label: xLabel },
          ...series.map((s) => ({
            label: s.label,
            stroke: COLORS[s.kind],
            width: s.kind === 'meas' ? 0 : 2,
            spanGaps: true,
            dash: s.kind === 'theory' ? [6, 4] : undefined,
            points: { show: true, size: s.kind === 'meas' ? 8 : 5, fill: COLORS[s.kind] },
          })),
        ],
      },
      data as uPlot.AlignedData,
      el,
    )
    const ro = new ResizeObserver(() => plot.setSize({ width: Math.max(280, el.clientWidth), height }))
    ro.observe(el)
    return () => {
      ro.disconnect()
      plot.destroy()
    }
  }, [title, xLabel, yLabel, series, height])

  return <div ref={ref} dir="ltr" className="chart" data-testid={`chart-${title}`} />
}
