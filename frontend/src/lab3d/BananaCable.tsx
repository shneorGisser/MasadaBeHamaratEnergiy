import { useMemo } from 'react'
import { CatmullRomCurve3, Vector3 } from 'three'

/**
 * A laboratory patch cord: a banana plug standing in each socket, the lead rising out of the
 * plug and draping between them under its own weight. The drape is a static shape (a sag
 * proportional to the span, never through the bench top) — not a physics simulation; the
 * bench has no cable dragging, so a solver would add a dependency without adding behaviour.
 */
// bench units (the equipment is drawn ≈ 3× life size so it stays readable from above)
const LEAD_R = 0.012
const PLUG_R = 0.022
const PLUG_L = 0.08
const RISE = 0.12 // the lead leaves the plug vertically before it bends

export default function BananaCable({
  a,
  b,
  color,
  highlight,
}: {
  a: [number, number, number]
  b: [number, number, number]
  color: string
  highlight: boolean
}) {
  const curve = useMemo(() => {
    const pa = new Vector3(a[0], a[1] + PLUG_L, a[2])
    const pb = new Vector3(b[0], b[1] + PLUG_L, b[2])
    const span = pa.distanceTo(pb)
    const lowest = Math.min(pa.y, pb.y)
    const sagY = Math.max(LEAD_R + 0.002, lowest + RISE - 0.35 * span)
    const mid = pa.clone().lerp(pb, 0.5)
    mid.y = Math.min(mid.y, sagY)
    const upA = pa.clone().add(new Vector3(0, RISE, 0))
    const upB = pb.clone().add(new Vector3(0, RISE, 0))
    return new CatmullRomCurve3([pa, upA, mid, upB, pb], false, 'centripetal')
  }, [a, b])
  const radius = highlight ? LEAD_R * 1.8 : LEAD_R
  const emissive = highlight ? '#ff3b2f' : '#000000'
  return (
    <group>
      <mesh castShadow>
        <tubeGeometry args={[curve, 48, radius, 8, false]} />
        <meshStandardMaterial color={highlight ? '#e74c3c' : color} roughness={0.55} emissive={emissive} emissiveIntensity={highlight ? 0.5 : 0} />
      </mesh>
      {[a, b].map((p, i) => (
        <group key={i} position={[p[0], p[1] + PLUG_L / 2, p[2]]}>
          <mesh>
            <cylinderGeometry args={[PLUG_R, PLUG_R * 0.85, PLUG_L, 12]} />
            <meshStandardMaterial color={highlight ? '#e74c3c' : color} roughness={0.4} />
          </mesh>
          <mesh position={[0, -PLUG_L / 2 - 0.012, 0]}>
            <cylinderGeometry args={[0.007, 0.007, 0.024, 8]} />
            <meshStandardMaterial color="#c9a14a" metalness={0.8} roughness={0.3} />
          </mesh>
        </group>
      ))}
    </group>
  )
}
