import { Html, Line, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Group } from 'three'
import { api } from '../api/client'
import { useProject } from '../api/hooks'
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
/** slider ranges of the DC-bench rheostats (field, extra armature resistance, load) */
const RHEO_MAX: Record<string, number> = { Rf: 1000, Rx: 60, RL: 2000 }
/** machines drawn as a motor/generator coupled to a brake or drive on a common base */
const ROTATING = new Set(['motor3', 'woundmotor3', 'syncmachine3', 'dcmachine'])
const SIZE: Record<string, [number, number, number]> = {
  source3: [1.1, 0.7, 0.6],
  source_dc: [0.7, 0.4, 0.4],
  switch3: [0.6, 0.4, 0.5],
  transformer3: [1.2, 1.0, 0.8],
  motor3: [1.6, 0.7, 0.7],
  syncmachine3: [1.6, 0.7, 0.7],
  woundmotor3: [1.6, 0.7, 0.7],
  dcmachine: [1.6, 0.7, 0.7],
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
  if (c.type === 'motor3') return `${fmt(r.n)} rpm · ${fmt(r.M, 3)} N·m`
  if (c.type === 'woundmotor3') return `${fmt(r.n)} rpm · ${fmt(r.M, 3)} N·m · f2 ${fmt(r.f_rotor, 3)} Hz`
  if (c.type === 'dcmachine') return `${fmt(r.n)} rpm · ${fmt(r.M, 3)} N·m`
  if (c.type === 'syncmachine3') return `${fmt(r.n)} rpm · ${fmt(r.f)} Hz · If ${fmt(r.If, 3)} A`
  return null
}

/**
 * Motor + magnetic-powder brake on a common base. The coupling turns at a slowed-down rate
 * proportional to the solved speed (a visual cue only; 1500 rpm shown as 1 rev/s).
 */
function MotorBrake({
  rpm,
  emissive,
  onClick,
  bodyColor = '#5f7d95',
  finColor = '#4f6a80',
  loadColor = '#8c8f91',
}: {
  rpm: number
  emissive: string
  onClick: (e: ThreeEvent<MouseEvent>) => void
  bodyColor?: string
  finColor?: string
  loadColor?: string
}) {
  const coupling = useRef<Group>(null)
  useFrame((state, dt) => {
    if (!coupling.current || rpm <= 0) return
    coupling.current.rotation.x += (rpm / 1500) * 2 * Math.PI * dt
    state.invalidate()
  })
  return (
    <group onClick={onClick}>
      <mesh position={[0, 0.05, 0]}>
        <boxGeometry args={[1.6, 0.1, 0.7]} />
        <meshStandardMaterial color="#3a3f42" emissive={emissive} />
      </mesh>
      {/* motor: finned cylinder along x */}
      <mesh position={[-0.35, 0.4, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.27, 0.27, 0.7, 32]} />
        <meshStandardMaterial color={bodyColor} metalness={0.3} roughness={0.6} emissive={emissive} />
      </mesh>
      {[-0.6, -0.45, -0.3, -0.15].map((x) => (
        <mesh key={x} position={[x, 0.4, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.3, 0.3, 0.03, 32]} />
          <meshStandardMaterial color={finColor} emissive={emissive} />
        </mesh>
      ))}
      <mesh position={[-0.35, 0.72, 0]}>
        <boxGeometry args={[0.26, 0.12, 0.26]} />
        <meshStandardMaterial color={finColor} emissive={emissive} />
      </mesh>
      {/* shaft + coupling */}
      <group ref={coupling} position={[0.12, 0.4, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.035, 0.035, 0.3, 12]} />
          <meshStandardMaterial color="#b9b9b9" metalness={0.8} roughness={0.3} />
        </mesh>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.09, 0.09, 0.08, 6]} />
          <meshStandardMaterial color="#d1a43c" />
        </mesh>
        <mesh position={[0, 0.09, 0]}>
          <boxGeometry args={[0.04, 0.04, 0.04]} />
          <meshStandardMaterial color="#c0392b" />
        </mesh>
      </group>
      {/* magnetic-powder brake */}
      <mesh position={[0.5, 0.4, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.24, 0.24, 0.4, 32]} />
        <meshStandardMaterial color={loadColor} metalness={0.5} roughness={0.4} emissive={emissive} />
      </mesh>
    </group>
  )
}

function Equipment({
  c,
  pos,
  selected,
  onSelect,
  live,
  switchClosed,
  variacFrac,
  showLabel,
}: {
  c: CComponent
  pos: [number, number, number]
  selected: boolean
  onSelect: () => void
  live: LivePoint | null
  switchClosed: boolean
  variacFrac: number
  showLabel: boolean
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
      {c.type === 'motor3' || c.type === 'woundmotor3' ? (
        <MotorBrake rpm={Number(live?.readings?.[c.id]?.n ?? 0)} emissive={emissive} onClick={click} />
      ) : c.type === 'dcmachine' ? (
        // DC machine (brown-grey frame) on the servo brake / drive
        <MotorBrake
          rpm={Math.abs(Number(live?.readings?.[c.id]?.n ?? 0))}
          emissive={emissive}
          onClick={click}
          bodyColor="#7d6f62"
          finColor="#685c51"
          loadColor="#3b3f44"
        />
      ) : c.type === 'syncmachine3' ? (
        // synchronous machine (blue-grey) coupled to the servo drive (dark)
        <MotorBrake
          rpm={Number(live?.readings?.[c.id]?.n ?? 0)}
          emissive={emissive}
          onClick={click}
          bodyColor="#6f8fa8"
          finColor="#59768c"
          loadColor="#3b3f44"
        />
      ) : c.type === 'transformer3' ? (
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
      {showLabel && (
      <Html position={[0, (c.type === 'transformer3' ? 1.1 : ROTATING.has(c.type) ? 0.8 : h) + 0.25, 0]} center distanceFactor={7} zIndexRange={[10, 0]}>
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
      )}
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
  // drei <Html> labels mounted in the canvas's very first commit lose their content (the first
  // one in the list never rendered). Mounting them after the first frame avoids that.
  const [labels, setLabels] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setLabels(true))
    return () => cancelAnimationFrame(id)
  }, [])
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
    const top = c.type === 'transformer3' || ROTATING.has(c.type) ? 0.1 : h
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
          showLabel={labels}
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
  const motor = circuit?.components.find((c) => c.type === 'motor3' || c.type === 'woundmotor3')
  const project = useProject(projectId)
  const mN = project.data?.derived.M_n ?? 1
  const [brake, setBrake] = useState<number | null>(null)
  const [locked, setLocked] = useState<boolean | null>(null)
  const mLoad = brake ?? Number(motor?.params.M_load ?? 0)
  const isLocked = locked ?? Boolean(motor?.params.locked ?? false)
  const brakeMax = Math.round(3 * mN * 100) / 100
  const [angle, setAngle] = useState<number | null>(null)
  const rotorAngle = angle ?? Number(motor?.params.angle ?? 0)
  const wound = motor?.type === 'woundmotor3'
  const sm = circuit?.components.find((c) => c.type === 'syncmachine3')
  const spec = project.data?.spec as { nameplate?: { If_n?: number; P_n?: number } } | undefined
  const ifMax = 1.5 * (spec?.nameplate?.If_n ?? 4)
  const pMax = 1.5 * (spec?.nameplate?.P_n ?? 300)
  const [iF, setIF] = useState<number | null>(null)
  const [pShaft, setPShaft] = useState<number | null>(null)
  const fieldI = iF ?? Number(sm?.params.I_f ?? 0)
  const shaftP = pShaft ?? Number(sm?.params.P_shaft ?? 0)
  const onGrid = Boolean(source)
  // DC machine bench: the servo either brakes (motor tests) or drives (generator tests)
  const dcm = circuit?.components.find((c) => c.type === 'dcmachine')
  const dcSpeedMode = dcm?.params.speed_mode === 'speed'
  const nMax = Number((spec as { nameplate?: { n_max?: number } } | undefined)?.nameplate?.n_max ?? 3000)
  const [dcBrake, setDcBrake] = useState<number | null>(null)
  const [dcSpeed, setDcSpeed] = useState<number | null>(null)
  const dcM = dcBrake ?? Number(dcm?.params.M_load ?? 0)
  const dcN = dcSpeed ?? Number(dcm?.params.n_set ?? 0)
  const dcSources = useMemo(() => circuit?.components.filter((c) => c.type === 'source_dc') ?? [], [circuit])
  const rheostats = useMemo(() => (dcm ? circuit?.components.filter((c) => c.type === 'resistor') ?? [] : []), [circuit, dcm])
  const [dcU, setDcU] = useState<Record<string, number>>({})
  const [rheo, setRheo] = useState<Record<string, number>>({})

  useEffect(() => {
    if (!circuit) return
    const overrides: Record<string, Record<string, unknown>> = {}
    if (source) overrides[source.id] = { U_line: u }
    for (const [id, closed] of Object.entries(switches)) overrides[id] = { closed }
    if (motor) overrides[motor.id] = wound && isLocked ? { M_load: mLoad, locked: true, angle: rotorAngle } : { M_load: mLoad, locked: isLocked }
    if (sm) overrides[sm.id] = onGrid ? { I_f: fieldI, P_shaft: shaftP } : { I_f: fieldI }
    if (dcm) overrides[dcm.id] = dcSpeedMode ? { n_set: dcN } : { M_load: dcM }
    for (const [id, v] of Object.entries(dcU)) overrides[id] = { U: v }
    for (const [id, v] of Object.entries(rheo)) overrides[id] = { R: v }
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
  }, [circuit, source, u, switches, motor, mLoad, isLocked, wound, rotorAngle, sm, fieldI, shaftP, onGrid, dcm, dcSpeedMode, dcN, dcM, dcU, rheo, projectId, kind])

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
        {motor && (
          <>
            <label className="row" style={{ gap: 6 }}>
              בלם ({motor.id}): <strong className="num" data-testid="brake-value">{fmt(mLoad, 3)} N·m</strong>
              <input
                type="range"
                min={0}
                max={brakeMax}
                step={0.01}
                value={mLoad}
                disabled={isLocked}
                onChange={(e) => setBrake(Number(e.target.value))}
                data-testid="brake"
                aria-label="מומנט הבלם"
                style={{ width: 180 }}
              />
            </label>
            <label className="row" style={{ gap: 4 }}>
              <input type="checkbox" checked={isLocked} data-testid="locked" onChange={(e) => setLocked(e.target.checked)} />
              רוטור נעול
            </label>
            {wound && isLocked && (
              <label className="row" style={{ gap: 6 }}>
                זווית הרוטור: <strong className="num" data-testid="angle-value">{fmt(rotorAngle)}°</strong>
                <input
                  type="range"
                  min={0}
                  max={360}
                  step={5}
                  value={rotorAngle}
                  onChange={(e) => setAngle(Number(e.target.value))}
                  data-testid="angle"
                  aria-label="זווית הרוטור"
                  style={{ width: 160 }}
                />
              </label>
            )}
          </>
        )}
        {sm && (
          <>
            <label className="row" style={{ gap: 6 }}>
              עירור ({sm.id}): <strong className="num" data-testid="field-value">{fmt(fieldI, 3)} A</strong>
              <input
                type="range"
                min={0}
                max={ifMax}
                step={0.01}
                value={fieldI}
                onChange={(e) => setIF(Number(e.target.value))}
                data-testid="field"
                aria-label="זרם העירור"
                style={{ width: 180 }}
              />
            </label>
            {onGrid && (
              <label className="row" style={{ gap: 6 }}>
                הספק בציר: <strong className="num" data-testid="shaft-value">{fmt(shaftP)} W</strong>
                <input
                  type="range"
                  min={-pMax}
                  max={pMax}
                  step={1}
                  value={shaftP}
                  onChange={(e) => setPShaft(Number(e.target.value))}
                  data-testid="shaft"
                  aria-label="הספק בציר"
                  style={{ width: 160 }}
                />
              </label>
            )}
          </>
        )}
        {dcSources.map((d) => {
          const nominalU = Number(d.params.U ?? 0)
          const v = dcU[d.id] ?? nominalU
          return (
            <label key={d.id} className="row" style={{ gap: 6 }}>
              {d.label || d.id}: <strong className="num" data-testid={`dc-value-${d.id}`}>{fmt(v)} V</strong>
              <input
                type="range"
                min={0}
                max={Math.max(Math.round(nominalU * 1.3), 1)}
                step={1}
                value={v}
                onChange={(e) => setDcU({ ...dcU, [d.id]: Number(e.target.value) })}
                data-testid={`dc-${d.id}`}
                aria-label={`מתח ${d.id}`}
                style={{ width: 140 }}
              />
            </label>
          )
        })}
        {rheostats.map((r) => {
          const max = RHEO_MAX[r.id] ?? 1000
          const set = Number(r.params.R ?? 0)
          const v = rheo[r.id] ?? Math.min(set, max)
          return (
            <label key={r.id} className="row" style={{ gap: 6 }}>
              {r.label || r.id}: <strong className="num" data-testid={`rheo-value-${r.id}`}>{set > max && rheo[r.id] === undefined ? 'פתוח' : `${fmt(v)} Ω`}</strong>
              <input
                type="range"
                min={0}
                max={max}
                step={max / 200}
                value={v}
                onChange={(e) => setRheo({ ...rheo, [r.id]: Number(e.target.value) })}
                data-testid={`rheo-${r.id}`}
                aria-label={r.label || r.id}
                style={{ width: 140 }}
              />
            </label>
          )
        })}
        {dcm &&
          (dcSpeedMode ? (
            <label className="row" style={{ gap: 6 }}>
              סרוו ({dcm.id}): <strong className="num" data-testid="speed-value">{fmt(dcN)} rpm</strong>
              <input
                type="range"
                min={0}
                max={nMax}
                step={10}
                value={dcN}
                onChange={(e) => setDcSpeed(Number(e.target.value))}
                data-testid="speed"
                aria-label="מהירות הסרוו"
                style={{ width: 180 }}
              />
            </label>
          ) : (
            <label className="row" style={{ gap: 6 }}>
              בלם ({dcm.id}): <strong className="num" data-testid="brake-value">{fmt(dcM, 3)} N·m</strong>
              <input
                type="range"
                min={0}
                max={Math.round(2 * mN * 100) / 100}
                step={0.01}
                value={dcM}
                onChange={(e) => setDcBrake(Number(e.target.value))}
                data-testid="brake"
                aria-label="מומנט הבלם"
                style={{ width: 180 }}
              />
            </label>
          ))}
        <span className="grow" />
        {live && <StatusBadge status={live.status} />}
        <span className="badge sim">נקודת עבודה חיה מהפותר · לא נשמרת</span>
      </div>
      {error != null && <ErrorBox error={error} />}
      {live?.error && <div className="alert error">{live.error.message}</div>}
      {live?.warnings
        ?.filter((w) => w.code !== 'undefined_reading')
        .map((w) => (
          <div key={w.code + w.message} className="alert warn" data-testid={`live-warning-${w.code}`}>
            {w.message}
          </div>
        ))}
      <div className="lab-canvas" dir="ltr">
        <Canvas camera={{ position: [0, 6.5, 7.5], fov: 38 }} dpr={[1, 1.5]} frameloop="demand">
          <Scene circuit={circuit} live={live} switches={switches} variacFrac={u / uMax} />
        </Canvas>
      </div>
      <p className="muted small">
        הציוד נבנה מאותו מסמך מעגל שהסכמה הדו-ממדית עורכת; סיבוב הצימוד מואט להמחשה (1500 סל״ד = סיבוב לשנייה); החוטים בשולחן הם חוטי המעגל. מכשירים אידיאליים — הקריאות הן פתרון הפותר, לא אנימציה. המראה סכמטי עד לקבלת תמונות הציוד.
      </p>
    </div>
  )
}
