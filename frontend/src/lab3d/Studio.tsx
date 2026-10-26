/** Studio lighting of the 3D bench (offline: light panels, no HDR download). */
import { ContactShadows, Environment, Lightformer } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { memo, useMemo } from 'react'

/**
 * Studio lighting built from light panels (soft reflections on the equipment without downloading
 * an HDR file — the bench must work offline) and a contact shadow under the equipment. Both are
 * rendered once and memoised: the scene re-renders on every slider step.
 */
export const Studio = memo(function Studio() {
  // A software renderer (no GPU: SwiftShader/llvmpipe, e.g. a VM or CI) cannot afford the
  // environment map at the frame rate of a turning machine; it keeps the plain lights.
  const gl = useThree((s) => s.gl)
  const software = useMemo(() => {
    const ctx = gl.getContext()
    const ext = ctx.getExtension('WEBGL_debug_renderer_info')
    const name = String(ext ? ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL) : ctx.getParameter(ctx.RENDERER))
    return /swiftshader|llvmpipe|software/i.test(name)
  }, [gl])
  if (software) return null
  return (
    <>
      <Environment resolution={64} frames={1}>
        <Lightformer intensity={2} position={[0, 6, 0]} rotation-x={Math.PI / 2} scale={[12, 6, 1]} />
        <Lightformer intensity={0.8} position={[-8, 3, 4]} rotation-y={Math.PI / 2} scale={[8, 3, 1]} />
        <Lightformer intensity={0.8} position={[8, 3, -4]} rotation-y={-Math.PI / 2} scale={[8, 3, 1]} />
      </Environment>
      <ContactShadows position={[0, 0.002, 0]} scale={30} opacity={0.45} blur={2.4} far={3} resolution={256} frames={1} />
    </>
  )
})

