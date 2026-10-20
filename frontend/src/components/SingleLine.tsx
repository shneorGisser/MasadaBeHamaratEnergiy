import type { ResultTable } from '../api/types'
import { fmt } from '../format'

/**
 * Single-line diagram of the lab feeder (network module), annotated with the run's results:
 * load flow → bus voltage and voltage drop, branch loading; short circuit → I''k3 max and
 * I''k1 min. Drawn left to right (the convention of single-line diagrams, also in RTL pages).
 */
const BUS_X = [70, 300, 520, 740]
const bx = (i: number): number => BUS_X[i] ?? 0
const BUS_NAMES = ['B0 מ״ג', 'B1 לוח ראשי', 'B2 לוח המעבדה', 'B3 עמדה']
const Y = 70 // conductor height
const BAR = 46 // half the bus-bar length

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export default function SingleLine({ tables }: { tables: ResultTable[] }) {
  const buses = tables.find((t) => t.id === 'buses')
  const branches = tables.find((t) => t.id === 'branches')
  const sc = tables.find((t) => t.id === 'sc')
  if (!buses && !sc) return null
  const busNote = (i: number): string[] => {
    if (buses) {
      const r = buses.rows[i] ?? {}
      const u = num(r.U)
      const du = num(r.du)
      return [u === null ? '' : `${fmt(u)} V`, du === null ? '' : `ΔU ${du.toFixed(2)} %`]
    }
    const r = sc?.rows[i] ?? {}
    const a = num(r.Ik3_max)
    const b = num(r.Ik1_min)
    return [a === null ? '' : `I''k3 ${fmt(a)} kA`, b === null ? '' : `I''k1,min ${fmt(b)} kA`]
  }
  const dropWarn = (i: number) => buses !== undefined && (num(buses.rows[i]?.du) ?? 0) > 4
  const loading = (i: number) => {
    const v = num(branches?.rows[i]?.loading)
    return v === null ? null : v
  }
  const midT = (bx(0) + bx(1)) / 2
  return (
    <section className="card" data-testid="single-line">
      <h2>תרשים חד-קווי</h2>
      <svg viewBox="0 0 820 190" width="100%" role="img" aria-label="תרשים חד-קווי של הזנת המעבדה" style={{ direction: 'ltr', maxHeight: 240 }}>
        {/* grid infeed */}
        <g stroke="var(--ink)" strokeWidth={1.6} fill="none">
          <rect x={bx(0) - 40} y={Y - 14} width={28} height={28} />
          <path d={`M${bx(0) - 40} ${Y + 14} L${bx(0) - 12} ${Y - 14} M${bx(0) - 40} ${Y} L${bx(0) - 26} ${Y - 14} M${bx(0) - 26} ${Y + 14} L${bx(0) - 12} ${Y}`} />
          <line x1={bx(0) - 12} y1={Y} x2={bx(0)} y2={Y} />
          {/* transformer: two overlapping circles */}
          <line x1={bx(0)} y1={Y} x2={midT - 26} y2={Y} />
          <circle cx={midT - 10} cy={Y} r={16} />
          <circle cx={midT + 10} cy={Y} r={16} />
          <line x1={midT + 26} y1={Y} x2={bx(1)} y2={Y} />
          {/* cables */}
          <line x1={bx(1)} y1={Y} x2={bx(2)} y2={Y} strokeDasharray="0" />
          <line x1={bx(2)} y1={Y} x2={bx(3)} y2={Y} />
          {/* loads */}
          {[2, 3].map((i) => (
            <g key={i}>
              <line x1={bx(i) + 22} y1={Y} x2={bx(i) + 22} y2={Y + 30} />
              <path d={`M${bx(i) + 15} ${Y + 24} L${bx(i) + 22} ${Y + 36} L${bx(i) + 29} ${Y + 24} Z`} fill="var(--ink)" />
            </g>
          ))}
        </g>
        {/* bus bars */}
        {BUS_X.map((x, i) => (
          <g key={i}>
            <line x1={x} y1={Y - BAR / 2} x2={x} y2={Y + BAR / 2} stroke={dropWarn(i) ? 'var(--warn)' : 'var(--panel)'} strokeWidth={6} />
            <text x={x} y={Y - BAR / 2 - 8} textAnchor="middle" fontSize={13} fill="var(--ink)" fontWeight={600}>
              {BUS_NAMES[i]}
            </text>
            {busNote(i).map((s, k) => (
              <text key={k} x={x} y={Y + BAR / 2 + 42 + k * 17} textAnchor="middle" fontSize={13} fill={dropWarn(i) ? 'var(--warn)' : 'var(--sim)'} fontFamily="var(--mono)" data-testid={`sld-bus-${i}-${k}`}>
                {s}
              </text>
            ))}
          </g>
        ))}
        <text x={midT} y={Y - 26} textAnchor="middle" fontSize={12} fill="var(--ink)">
          Dyn{loading(0) !== null ? ` · ${loading(0)!.toFixed(0)} %` : ''}
        </text>
        {[1, 2].map((i) => (
          <text key={i} x={(bx(i) + bx(i + 1)) / 2} y={Y - 8} textAnchor="middle" fontSize={12} fill="var(--ink)">
            {`C${i}`}
            {loading(i) !== null ? ` · ${loading(i)!.toFixed(0)} %` : ''}
          </text>
        ))}
      </svg>
    </section>
  )
}
