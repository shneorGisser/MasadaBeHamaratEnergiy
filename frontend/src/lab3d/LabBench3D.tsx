import { Html, Line, OrbitControls } from '@react-three/drei'
import { Canvas, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { RunStatus } from '../api/types'
import { ErrorBox } from '../components/ErrorBox'
import StatusBadge from '../components/StatusBadge'
import { fmt } from '../format'
import { useCircuit } from '../schematic/hooks'
import type { CComponent, CircuitModel } from '../schematic/model'
import { terminalSlots } from '../schematic/slots'
import { useSelection } from '../selection'

/** Live operating point returned by the solver (never a scripted animation). */
interface LivePoint {
  status: RunStatus
  persisted: false
  source: 'simulation'
  readings?: Record<string, Record<string, number | null>>
  warnings?: { code: string; message: string }[]
  error?: { message: string }
}

const SCALE = 0.01 // schematic units → metres on the bench
const SIZE: Record<string, [number, number, number]> = {
  source3: [1.1, 0.7, 0.6],
  source_dc: [0.7, 0.4, 0.4],
  switch3: [0.6, 0.4, 0.5],
  transformer3: [1.2, 1.0, 0.8],
  load3: [1.0, 0.5, 0.7],
  resistor: [0.4, 0.2, 0.2],
  inductor: [0.4, 0.3, 0.3],
  capacitor: [0.3, 0.3, 0.3],
  ammeter: [0.5, 0.4, 0.3],
  voltmeter: [0.5, 0.4, 0.3],
  wattmeter: [0.6, 0.4, 0.35],
}

function readingText(c: CComponent, live: LivePoint | null): string | null {
  const r = live?.readings?.[c.id]
  if (!r) return null
  if (c.type === 'ammeter') return `${fmt(r.I)} A`
  if (c.type === 'voltmeter') return r.U === null ? 'לא מוגדר' : `${fmt(r.U)} V`
  if (c.type === 'wattmeter') return r.P === null ? 'לא מוגדר' : `${fmt(r.P)} W · cos φ ${fmt(r.pf, 3)}`
  return null
}

function Equipment({
  c,
  pos,
  selected,
  onSelect,
  live,
  switchClosed,
  variacFrac,
}: {
  c: CComponent
  pos: [number, number, number]
  selected: boolean
  onSelect: () => void
  live: LivePoint | null
  switchClosed: boolean
  variacFrac: number
}) {
  const [w, h, d] = SIZE[c.type] ?? [0.4, 0.3, 0.3]
  const click = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    onSelect()
  }
  const emissive = selected ? '#2b6f70' : '#000000'
  const reading = readingText(c, live)
  return (
    <group position={pos}>
      {c.type === 'transformer3' ? (
        <group onClick={click}>
          <mesh position={[0, 0.05, 0]}>
            <boxGeometry args={[w, 0.1, d]} />
            <meshStandardMaterial color="#3a3f42" emissive={emissive} />
          </mesh>
          {[-0.4, 0, 0.4].map((x) => (
            <group key={x}>
              <mesh position={[x, 0.5, 0]}>
                <boxGeometry args={[0.12, 0.8, 0.12]} />
                <meshStandardMaterial color="#555b60" emissive={emissive} />
              </mesh>
              <mesh position={[x, 0.42, 0]}>
                <cylinderGeometry args={[0.17, 0.17, 0.42, 24]} />
                <meshStandardMaterial color="#b8733a" metalness={0.4} roughness={0.5} emissive={emissive} />
              </mesh>
              <mesh position={[x, 0.7, 0]}>
                <cylinderGeometry args={[0.14, 0.14, 0.2, 24]} />
                <meshStandardMaterial color="#c98a4b" metalness={0.4} roughness={0.5} emissive={emissive} />
              </mesh>
            </group>
          ))}
          <mesh position={[0, 0.95, 0]}>
            <boxGeometry args={[w, 0.1, 0.14]} />
            <meshStandardMaterial color="#555b60" emissive={emissive} />
          </mesh>
        </group>
      ) : (
        <mesh position={[0, h / 2, 0]} onClick={click}>
          <boxGeometry args={[w, h, d]} />
          <meshStandardMaterial
            color={c.type === 'source3' ? '#6c7a80' : c.type === 'load3' ? '#7d5a3c' : c.type === 'switch3' ? '#2f3437' : '#e8e6df'}
            emissive={emissive}
          />
        </mesh>
      )}
      {c.type === 'source3' && (
        <mesh position={[0, h + 0.05, 0]} rotation={[0, -variacFrac * Math.PI * 1.5, 0]} onClick={click}>
          <cylinderGeometry args={[0.18, 0.2, 0.1, 6]} />
          <meshStandardMaterial color="#1b1b1b" />
        </mesh>
      )}
      {c.type === 'switch3' && (
        <mesh position={[0, h + 0.1, 0]} rotation={[switchClosed ? -0.6 : 0.6, 0, 0]} onClick={click}>
          <boxGeometry args={[0.08, 0.25, 0.08]} />
          <meshStandardMaterial color={switchClosed ? '#c0392b' : '#7f8c8d'} />
        </mesh>
      )}
      <Html position={[0, (c.type === 'transformer3' ? 1.1 : h) + 0.25, 0]} center distanceFactor={7} zIndexRange={[10, 0]}>
        <button
          className={`lab-label${selected ? ' selected' : ''}`}
          data-testid={`eq-${c.id}`}
          data-selected={selected}
          onClick={onSelect}
        >
          <strong>{c.id}</strong>
          {reading !== null && (
            <span className="lab-reading" data-testid={`reading-${c.id}`}>
              {reading}
            </span>
          )}
        </button>
      </Html>
    </group>
  )
}

function Scene({
  circuit,
  live,
  switches,
  variacFrac,
}: {
  circuit: CircuitModel
  live: LivePoint | null
  switches: Record<string, boolean>
  variacFrac: number
}) {
  const selected = useSelection((s) => s.selected)
  const select = useSelection((s) => s.select)
  const layout = circuit.layout
  const xs = Object.values(layout).map((p) => p.x)
  const ys = Object.values(layout).map((p) => p.y)
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2
  const posOf = (id: string): [number, number, number] => {
    const p = layout[id] ?? { x: cx, y: cy }
    return [(p.x - cx) * SCALE * 1.4, 0, (p.y - cy) * SCALE * 1.4]
  }
  const byId = new Map(circuit.components.map((c) => [c.id, c]))
  const terminalPos = (cid: string, t: string): [number, number, number] => {
    const c = byId.get(cid)
    const base = posOf(cid)
    if (!c) return base
    const [w, h, d] = SIZE[c.type] ?? [0.4, 0.3, 0.3]
    const slot = terminalSlots(c.type, [t])[t] ?? { side: 'left', at: 0.5 }
    const along = (slot.at - 0.5) * (slot.side === 'left' || slot.side === 'right' ? d : w)
    const top = c.type === 'transformer3' ? 0.1 : h
    if (slot.side === 'left') return [base[0] - w / 2, top, base[2] + along]
    if (slot.side === 'right') return [base[0] + w / 2, top, base[2] + along]
    return [base[0] + along, top, base[2] + d / 2]
  }
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 8, 5]} intensity={1.2} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} onClick={() => select(null)}>
        <planeGeometry args={[30, 16]} />
        <meshStandardMaterial color="#c9b48f" />
      </mesh>
      {circuit.components.map((c) => (
        <Equipment
          key={c.id}
          c={c}
          pos={posOf(c.id)}
          selected={selected === c.id}
          onSelect={() => select(c.id)}
          live={live}
          switchClosed={switches[c.id] ?? Boolean(c.params.closed ?? true)}
          variacFrac={variacFrac}
        />
      ))}
      {circuit.wires.map((w, i) => (
        <Line
          key={w.id}
          points={[terminalPos(w.a.component, w.a.terminal), terminalPos(w.b.component, w.b.terminal)]}
          color={['#8b4513', '#111111', '#777777', '#1f4fa3'][i % 4]}
          lineWidth={2}
        />
      ))}
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.1} />
    </>
  )
}

export default function LabBench3D({ projectId, kind }: { projectId: string; kind: string }) {
  const circuitQ = useCircuit(projectId, kind)
  const circuit = circuitQ.data?.circuit ?? null
  const source = circuit?.components.find((c) => c.type === 'source3')
  const nominal = Number(source?.params.U_line ?? 380)
  const [uLine, setULine] = useState<number | null>(null)
  const [switches, setSwitches] = useState<Record<string, boolean>>({})
  const [live, setLive] = useState<LivePoint | null>(null)
  const [error, setError] = useState<unknown>(null)
  const seq = useRef(0)
  const u = uLine ?? nominal
  const uMax = Math.max(Math.round(nominal * 1.25), 1)

  const switchComps = useMemo(() => circuit?.components.filter((c) => c.type === 'switch3') ?? [], [circuit])

  useEffect(() => {
    if (!circuit) return
    const overrides: Record<string, Record<string, unknown>> = {}
    if (source) overrides[source.id] = { U_line: u }
    for (const [id, closed] of Object.entries(switches)) overrides[id] = { closed }
    const my = ++seq.current
    const t = setTimeout(() => {
      api
        .post<LivePoint>(`/api/projects/${projectId}/circuits/${kind}/operating-point`, { overrides })
        .then((r) => {
          if (my === seq.current) {
            setLive(r)
            setError(null)
          }
        })
        .catch((e) => my === seq.current && setError(e))
    }, 150)
    return () => clearTimeout(t)
  }, [circuit, source, u, switches, projectId, kind])

  if (circuitQ.isLoading) return <p className="muted">טוען שולחן…</p>
  if (circuitQ.isError) return <ErrorBox error={circuitQ.error} />
  if (!circuit) return <p className="muted">לניסוי זה אין מעגל עריך.</p>

  return (
    <div className="stack" style={{ gap: 8 }} data-testid="lab3d">
      <div className="row small">
        {source && (
          <label className="row" style={{ gap: 6 }}>
            וריאק ({source.id}): <strong className="num" data-testid="variac-value">{fmt(u)} V</strong>
            <input
              type="range"
              min={0}
              max={uMax}
              step={1}
              value={u}
              onChange={(e) => setULine(Number(e.target.value))}
              data-testid="variac"
              aria-label="מתח הווריאק"
              style={{ width: 220 }}
            />
          </label>
        )}
        {switchComps.map((s) => {
          const closed = switches[s.id] ?? Boolean(s.params.closed ?? true)
          return (
            <label key={s.id} className="row" style={{ gap: 4 }}>
              <input
                type="checkbox"
                checked={closed}
                data-testid={`switch-${s.id}`}
                onChange={(e) => setSwitches({ ...switches, [s.id]: e.target.checked })}
              />
              מפסק {s.id} {closed ? 'סגור' : 'פתוח'}
            </label>
          )
        })}
        <span className="grow" />
        {live && <StatusBadge status={live.status} />}
        <span className="badge sim">נקודת עבודה חיה מהפותר · לא נשמרת</span>
      </div>
      {error != null && <ErrorBox error={error} />}
      {live?.error && <div className="alert error">{live.error.message}</div>}
      <div className="lab-canvas" dir="ltr">
        <Canvas camera={{ position: [0, 6.5, 7.5], fov: 38 }} dpr={[1, 1.5]} frameloop="demand">
          <Scene circuit={circuit} live={live} switches={switches} variacFrac={u / uMax} />
        </Canvas>
      </div>
      <p className="muted small">
        הציוד נבנה מאותו מסמך מעגל שהסכמה הדו-ממדית עורכת; החוטים בשולחן הם חוטי המעגל. מכשירים אידיאליים — הקריאות הן פתרון הפותר, לא אנימציה. המראה סכמטי עד לקבלת תמונות הציוד.
      </p>
    </div>
  )
}
