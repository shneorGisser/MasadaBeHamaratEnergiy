/**
 * Circuit symbols drawn after IEC 60617 conventions (resistor as a rectangle, meters as a circle
 * with the quantity's letter, machines as a circle with M/G and the kind of current, transformer
 * as two interlocking circles). Drawn here from the standard's shapes — no third-party artwork.
 * Every symbol sits in a 64×40 box and inherits `currentColor`.
 */
import type { ReactElement } from 'react'

const S = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const T = { fill: 'currentColor', fontSize: 11, fontWeight: 700, textAnchor: 'middle' as const, fontFamily: 'inherit' }

function Meter({ letter }: { letter: string }) {
  return (
    <>
      <circle cx={32} cy={20} r={15} {...S} />
      <text x={32} y={24.5} {...T} fontSize={14}>
        {letter}
      </text>
    </>
  )
}

function Machine({ letter, kind }: { letter: string; kind: string }) {
  return (
    <>
      <circle cx={32} cy={20} r={17} {...S} />
      <text x={32} y={20} {...T} fontSize={12}>
        {letter}
      </text>
      <text x={32} y={32} {...T} fontSize={9} fontWeight={600}>
        {kind}
      </text>
    </>
  )
}

const SYMBOLS: Record<string, () => ReactElement> = {
  resistor: () => (
    <>
      <path d="M2 20 H16 M48 20 H62" {...S} />
      <rect x={16} y={13} width={32} height={14} {...S} />
    </>
  ),
  inductor: () => (
    <path d="M2 20 H12 a5 5 0 0 1 10 0 a5 5 0 0 1 10 0 a5 5 0 0 1 10 0 a5 5 0 0 1 10 0 H62" {...S} />
  ),
  capacitor: () => <path d="M2 20 H28 M36 20 H62 M28 9 V31 M36 9 V31" {...S} />,
  ammeter: () => <Meter letter="A" />,
  voltmeter: () => <Meter letter="V" />,
  wattmeter: () => <Meter letter="W" />,
  source3: () => (
    <>
      <circle cx={32} cy={20} r={16} {...S} />
      <text x={32} y={18} {...T} fontSize={10}>
        3
      </text>
      <path d="M24 25 q4 -5 8 0 t8 0" {...S} strokeWidth={1.5} />
    </>
  ),
  source_dc: () => <path d="M2 20 H28 M36 20 H62 M28 6 V34 M36 13 V27 M14 9 h6 M17 6 v6" {...S} />,
  switch3: () => (
    <>
      {[10, 20, 30].map((y) => (
        <path key={y} d={`M4 ${y} H22 L42 ${y - 6} M44 ${y} H60`} {...S} strokeWidth={1.5} />
      ))}
      <path d="M32 7 V29" {...S} strokeWidth={1} strokeDasharray="2 2" />
    </>
  ),
  transformer3: () => (
    <>
      <circle cx={25} cy={20} r={12} {...S} />
      <circle cx={39} cy={20} r={12} {...S} />
    </>
  ),
  load3: () => (
    <>
      {[12, 28, 44].map((x) => (
        <rect key={x} x={x} y={8} width={9} height={24} {...S} strokeWidth={1.5} />
      ))}
    </>
  ),
  motor3: () => <Machine letter="M" kind="3~" />,
  woundmotor3: () => (
    <>
      <Machine letter="M" kind="3~" />
      {/* slip rings */}
      {[13, 20, 27].map((y) => (
        <circle key={y} cx={55} cy={y} r={2.2} {...S} strokeWidth={1.2} />
      ))}
    </>
  ),
  syncmachine3: () => <Machine letter="GS" kind="3~" />,
  dcmachine: () => <Machine letter="M/G" kind="=" />,
}

export default function CircuitSymbol({ type, size = 1 }: { type: string; size?: number }) {
  const draw = SYMBOLS[type]
  if (!draw) return null
  return (
    <svg width={64 * size} height={40 * size} viewBox="0 0 64 40" aria-hidden="true" className="sch-svg" data-symbol={type}>
      {draw()}
    </svg>
  )
}
