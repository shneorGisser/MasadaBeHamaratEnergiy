/** One piece of bench equipment (supply, meters, machines with brake/drive), drawn from its type. */
import { Html } from '@react-three/drei'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { useRef } from 'react'
import type { Group } from 'three'
import type { CComponent } from '../schematic/model'
import { ROTATING, SIZE, readingText, type LivePoint } from './live'
import { fmt } from '../format'
import { BrakeUnit, MeterModule, Variac } from './Panels'

/**
 * Motor + magnetic-powder brake on a common base. The coupling turns at a slowed-down rate
 * proportional to the solved speed (a visual cue only; 1500 rpm shown as 1 rev/s).
 */
export function MotorBrake({
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

/** What the module's own seven-segment readout shows: the number only, as on the real meter. */
function display(v: unknown, unit: string, digits = 4): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${fmt(v, digits)} ${unit}` : '----'
}

function meterDisplay(c: CComponent, live: LivePoint | null): string {
  const r = live?.readings?.[c.id]
  if (c.type === 'ammeter') return display(r?.I, 'A')
  if (c.type === 'voltmeter') return display(r?.U, 'V')
  return display(r?.P, 'W')
}

export function Equipment({
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
        <>
          <MotorBrake rpm={Number(live?.readings?.[c.id]?.n ?? 0)} emissive={emissive} onClick={click} />
          <BrakeUnit torque={display(live?.readings?.[c.id]?.M, 'Nm', 3)} speed={display(live?.readings?.[c.id]?.n, 'rpm', 4)} />
        </>
      ) : c.type === 'ammeter' || c.type === 'voltmeter' || c.type === 'wattmeter' ? (
        <MeterModule
          size={[w, h, d]}
          text={meterDisplay(c, live)}
          sockets={c.type === 'wattmeter' ? ['#c0392b', '#1b1b1b', '#c0392b', '#1b1b1b'] : ['#c0392b', '#1b1b1b']}
          emissive={emissive}
          onClick={click}
        />
      ) : c.type === 'source3' ? (
        <Variac size={[w, h, d]} emissive={emissive} onClick={click} />
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

