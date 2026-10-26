/**
 * Bench hardware modelled on the lab photos of 26.10.2026 (docs/lab-data-2026-exp2.md):
 * the Appli-com panel meters (red seven-segment readout on a light-grey module with banana
 * sockets), the Langlois HTN 450/8 variac (dark ribbed housing, carry handle, blue output
 * sockets) and the brake control unit with its torque and speed readouts. Shapes are
 * simplified; the readouts show the solved operating point, the same values as the labels.
 */
import type { ThreeEvent } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import { CanvasTexture, SRGBColorSpace } from 'three'

/** Text drawn into a canvas texture (no font download: works offline and in CI). A new texture
 * per text — readouts change only when the operating point is re-solved. */
function useReadout(text: string, color: string): CanvasTexture | null {
  const tex = useMemo(() => {
    if (typeof document === 'undefined') return null
    const canvas = document.createElement('canvas')
    canvas.width = 256
    canvas.height = 96
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.fillStyle = '#120806'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = color
    ctx.font = 'bold 64px "Courier New", monospace'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, canvas.width - 14, canvas.height / 2 + 3, canvas.width - 24)
    const t = new CanvasTexture(canvas)
    t.colorSpace = SRGBColorSpace
    return t
  }, [text, color])
  useEffect(() => () => tex?.dispose(), [tex])
  return tex
}

function Readout({
  text,
  position,
  size = [0.36, 0.13],
  color = '#ff3b2f',
}: {
  text: string
  position: [number, number, number]
  size?: [number, number]
  color?: string
}) {
  const tex = useReadout(text, color)
  return (
    <mesh position={position}>
      <planeGeometry args={size} />
      {tex ? <meshBasicMaterial map={tex} toneMapped={false} /> : <meshBasicMaterial color="#120806" />}
    </mesh>
  )
}

function Socket({ position, color }: { position: [number, number, number]; color: string }) {
  return (
    <mesh position={position} rotation={[Math.PI / 2, 0, 0]}>
      <cylinderGeometry args={[0.028, 0.028, 0.03, 12]} />
      <meshStandardMaterial color={color} roughness={0.4} />
    </mesh>
  )
}

/** Appli-com style panel meter: the readout on the upper front, sockets underneath. */
export function MeterModule({
  size,
  text,
  sockets,
  emissive,
  onClick,
}: {
  size: [number, number, number]
  text: string
  sockets: string[]
  emissive: string
  onClick: (e: ThreeEvent<MouseEvent>) => void
}) {
  const [w, h, d] = size
  const front = d / 2 + 0.002
  return (
    <group onClick={onClick}>
      <mesh position={[0, h / 2, 0]}>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color="#e4e6e5" roughness={0.7} emissive={emissive} />
      </mesh>
      {/* dark bezel around the display */}
      <mesh position={[0, h * 0.68, front]}>
        <planeGeometry args={[w * 0.82, h * 0.38]} />
        <meshStandardMaterial color="#2d3134" />
      </mesh>
      <Readout text={text} position={[0, h * 0.68, front + 0.002]} size={[w * 0.74, h * 0.28]} />
      {sockets.map((col, i) => (
        <Socket
          key={i}
          position={[(i - (sockets.length - 1) / 2) * (w / (sockets.length + 1)), h * 0.24, front + 0.01]}
          color={col}
        />
      ))}
    </group>
  )
}

/** Langlois HTN 450/8: tall dark housing with vertical ribs, a carry handle, blue sockets. */
export function Variac({
  size,
  emissive,
  onClick,
}: {
  size: [number, number, number]
  emissive: string
  onClick: (e: ThreeEvent<MouseEvent>) => void
}) {
  const [w, h, d] = size
  const ribs = 9
  return (
    <group onClick={onClick}>
      <mesh position={[0, h / 2, 0]}>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color="#2e3236" roughness={0.8} emissive={emissive} />
      </mesh>
      {Array.from({ length: ribs }, (_, i) => (
        <mesh key={i} position={[(i - (ribs - 1) / 2) * (w / (ribs + 1)), h * 0.45, d / 2 + 0.01]}>
          <boxGeometry args={[0.025, h * 0.72, 0.02]} />
          <meshStandardMaterial color="#202326" />
        </mesh>
      ))}
      {/* white top plate with the maker's label strip, handle bar */}
      <mesh position={[0, h + 0.005, 0]}>
        <boxGeometry args={[w * 0.96, 0.01, d * 0.96]} />
        <meshStandardMaterial color="#d9dbd8" />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * w * 0.32, h + 0.09, -d * 0.3]}>
          <boxGeometry args={[0.04, 0.18, 0.04]} />
          <meshStandardMaterial color="#9aa0a4" metalness={0.6} roughness={0.3} />
        </mesh>
      ))}
      <mesh position={[0, h + 0.18, -d * 0.3]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.025, 0.025, w * 0.68, 12]} />
        <meshStandardMaterial color="#9aa0a4" metalness={0.6} roughness={0.3} />
      </mesh>
      {/* output sockets U V W N and PE across the top of the front, as in the photo */}
      {['#2f6fd6', '#2f6fd6', '#2f6fd6', '#2f6fd6', '#d9c22e'].map((col, i) => (
        <Socket key={i} position={[(i - 2) * 0.14, h * 0.91, d / 2 + 0.02]} color={col} />
      ))}
    </group>
  )
}

/** Brake control unit (APB type): torque and speed readouts, beside the brake end. */
export function BrakeUnit({ torque, speed }: { torque: string; speed: string }) {
  return (
    <group position={[1.3, 0, 0.05]} rotation={[0, -0.35, 0]}>
      <mesh position={[0, 0.3, 0]}>
        <boxGeometry args={[0.7, 0.6, 0.3]} />
        <meshStandardMaterial color="#e4e6e5" roughness={0.7} />
      </mesh>
      <Readout text={torque} position={[0, 0.44, 0.152]} size={[0.5, 0.14]} />
      <Readout text={speed} position={[0, 0.24, 0.152]} size={[0.5, 0.14]} />
    </group>
  )
}
