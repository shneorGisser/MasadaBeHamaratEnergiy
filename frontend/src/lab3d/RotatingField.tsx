/**
 * X-ray of the induction motor on the bench: the stator coils of the three phases, the field
 * their currents make, and the rotor, at the live operating point.
 *
 * What it shows, in the machine's own terms:
 * - each coil's colour follows its phase current, i_x(t) = cos(ωt − φ_x) (red = positive,
 *   blue = negative, brightness = magnitude): every coil only pulses, none moves;
 * - the sum of the three pulsating MMFs is a field of constant size that turns: its p poles
 *   (N red, S blue) sit where MMF(θ) = Σ i_x·cos(p/2·θ − φ_x) is largest, θ_N = ωt/(p/2);
 * - the rotor turns at the solver's speed n, slower than the field (n_s = 120·f/p) by the slip
 *   s = (n_s − n)/n_s. The rotor currents have the frequency s·f — they exist only because the
 *   rotor lags.
 *
 * Time is slowed so the eye can follow (the field makes one electrical turn in 4 s). The ratio
 * n/n_s is the solver's; at a few percent slip the lag is slow to see, so the slip can be
 * magnified for viewing — the label says so whenever it is.
 */
import { Canvas, useFrame } from '@react-three/fiber'
import { useMemo, useRef, useState } from 'react'
import { Color, type Group, type Mesh, type MeshStandardMaterial } from 'three'
import { fmt } from '../format'

const F_VIS = 0.25 // shown electrical frequency [Hz]
const PHASE_OFF = [0, (2 * Math.PI) / 3, (4 * Math.PI) / 3]
const PHASE_NAME = ['U (L1)', 'V (L2)', 'W (L3)']
const POS = new Color('#e0473c')
const NEG = new Color('#2f6fd6')
const OFF = new Color('#3a3f44')

function Machine({ poles, ratio, magnify, playing }: { poles: number; ratio: number; magnify: number; playing: boolean }) {
  const pp = Math.max(1, Math.round(poles / 2))
  const t = useRef(0)
  const rotor = useRef<Group>(null)
  const field = useRef<Group>(null)
  const coils = useRef<(Mesh | null)[]>([])
  // coil sides: phase x, pole-pair m, polarity ±: centred at mechanical angle (φ_x + π·k)/pp
  const sides = useMemo(() => {
    const out: { phase: number; sign: number; angle: number }[] = []
    for (let x = 0; x < 3; x++)
      for (let k = 0; k < 2 * pp; k++) out.push({ phase: x, sign: k % 2 ? -1 : 1, angle: (PHASE_OFF[x]! + Math.PI * k) / pp })
    return out
  }, [pp])
  const slip = 1 - ratio
  const shownRatio = Math.max(-1, 1 - slip * magnify)

  useFrame((state, dt) => {
    if (playing) t.current += dt
    const we = 2 * Math.PI * F_VIS * t.current
    sides.forEach((s, i) => {
      const m = coils.current[i]
      if (!m) return
      const v = s.sign * Math.cos(we - PHASE_OFF[s.phase]!)
      const mat = m.material as MeshStandardMaterial
      mat.color.copy(OFF).lerp(v >= 0 ? POS : NEG, Math.abs(v))
      mat.emissive.copy(v >= 0 ? POS : NEG).multiplyScalar(0.35 * Math.abs(v))
    })
    // the field: N pole of pole pair 0 at θ = ωt/pp (mechanical, counter-clockwise)
    if (field.current) field.current.rotation.z = we / pp
    if (rotor.current) rotor.current.rotation.z = (we / pp) * shownRatio
    state.invalidate()
  })

  return (
    <group>
      {/* stator yoke */}
      <mesh>
        <torusGeometry args={[2.25, 0.32, 16, 96]} />
        <meshStandardMaterial color="#5f7d95" metalness={0.3} roughness={0.6} />
      </mesh>
      {sides.map((s, i) => (
        <mesh
          key={i}
          ref={(m) => {
            coils.current[i] = m
          }}
          position={[1.78 * Math.cos(s.angle), 1.78 * Math.sin(s.angle), 0]}
          rotation={[0, 0, s.angle]}
        >
          <boxGeometry args={[0.32, 0.22, 0.5]} />
          <meshStandardMaterial color={OFF} />
        </mesh>
      ))}
      {/* the rotating field: p poles in the air gap */}
      <group ref={field}>
        {Array.from({ length: 2 * pp }, (_, k) => {
          const a = (Math.PI * k) / pp
          return (
            <mesh key={k} position={[1.45 * Math.cos(a), 1.45 * Math.sin(a), 0.3]}>
              <sphereGeometry args={[0.17, 24, 16]} />
              <meshStandardMaterial color={k % 2 ? '#2f6fd6' : '#e0473c'} emissive={k % 2 ? '#123a7a' : '#7a1a12'} />
            </mesh>
          )
        })}
      </group>
      {/* cage rotor with a marker bar */}
      <group ref={rotor}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[1.18, 1.18, 0.55, 48]} />
          <meshStandardMaterial color="#8c8f91" metalness={0.5} roughness={0.4} />
        </mesh>
        {Array.from({ length: 16 }, (_, k) => {
          const a = (2 * Math.PI * k) / 16
          return (
            <mesh key={k} position={[1.05 * Math.cos(a), 1.05 * Math.sin(a), 0.29]}>
              <boxGeometry args={[0.07, 0.07, 0.04]} />
              <meshStandardMaterial color="#c98a4b" metalness={0.6} />
            </mesh>
          )
        })}
        <mesh position={[0.6, 0, 0.29]}>
          <boxGeometry args={[1.0, 0.1, 0.03]} />
          <meshStandardMaterial color="#f2c14e" emissive="#5a4410" />
        </mesh>
      </group>
    </group>
  )
}

export default function RotatingField({ poles, f, n }: { poles: number; f: number; n: number | null }) {
  const [open, setOpen] = useState(false)
  const [magnify, setMagnify] = useState(1)
  const [playing, setPlaying] = useState(() => {
    try {
      return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    } catch {
      return true
    }
  })
  const ns = (120 * f) / poles
  const ratio = n === null ? 0 : n / ns
  const s = 1 - ratio
  return (
    <details className="card" style={{ padding: 10 }} data-testid="rotating-field" onToggle={(e) => e.target === e.currentTarget && setOpen(e.currentTarget.open)}>
      <summary>מבט שקוף: השדה המסתובב והרוטור</summary>
      {open && (
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div className="lab-canvas" dir="ltr" style={{ width: 340, height: 340, flex: '0 0 auto' }}>
          <Canvas camera={{ position: [0, 0, 6.2], fov: 45 }} dpr={[1, 1.5]} frameloop="demand">
            <ambientLight intensity={0.5} />
            <directionalLight position={[3, 4, 6]} intensity={1} />
            <Machine poles={poles} ratio={ratio} magnify={magnify} playing={playing} />
          </Canvas>
        </div>
        <div className="stack grow small" style={{ gap: 6 }}>
          <dl className="kv">
            <dt>
              מהירות השדה <bdi dir="ltr">n_s = 120·f/p</bdi>
            </dt>
            <dd className="num">{fmt(ns)} rpm</dd>
            <dt>מהירות הרוטור n (מהפותר)</dt>
            <dd className="num">{n === null ? '—' : `${fmt(n)} rpm`}</dd>
            <dt>
              החלקה <bdi dir="ltr">s = (n_s − n)/n_s</bdi>
            </dt>
            <dd className="num" data-testid="rf-slip">{n === null ? '—' : fmt(s, 3)}</dd>
            <dt>
              תדר זרמי הרוטור <bdi dir="ltr">s·f</bdi>
            </dt>
            <dd className="num">{n === null ? '—' : `${fmt(s * f, 3)} Hz`}</dd>
          </dl>
          <p className="muted">
            כל סליל רק פועם, צבעו לפי זרם הפאזה שלו (<bdi dir="ltr">{PHASE_NAME.join(', ')}</bdi>). הסכום של שלושת השדות הפועמים הוא שדה בגודל קבוע שמסתובב: {poles} הקטבים (צפון אדום, דרום כחול) באמצע. הפס הצהוב
            מסמן את הרוטור: הוא מפגר אחרי השדה, ובגלל הפיגור נוצר בו זרם ומומנט.
          </p>
          <label className="row" style={{ gap: 6 }}>
            הגדלת ההחלקה לתצוגה: ×{magnify}
            <input type="range" dir="ltr" min={1} max={20} step={1} value={magnify} onChange={(e) => setMagnify(Number(e.target.value))} aria-label="הגדלת ההחלקה" />
          </label>
          {magnify > 1 && <span className="badge warn">להמחשה בלבד: הרוטור מוצג עם החלקה פי {magnify} מהמחושבת</span>}
          <button className="btn small" style={{ alignSelf: 'flex-start' }} onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            {playing ? 'עצירה' : 'הפעלה'}
          </button>
          <p className="muted">הזמן מואט: סיבוב חשמלי אחד של השדה ב-4 שניות.</p>
        </div>
      </div>
      )}
    </details>
  )
}
