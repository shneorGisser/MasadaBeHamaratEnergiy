import { Handle, type NodeProps } from '@xyflow/react'
import { POS, terminalSlots } from './slots'
import { fmt } from '../format'
import type { CompNode } from './model'

const SYMBOL: Record<string, string> = {
  source3: '3~',
  source_dc: '=',
  switch3: '⏻',
  transformer3: '⧚',
  motor3: 'M3~',
  syncmachine3: 'SG3~',
  woundmotor3: 'M3~ (טבעות)',
  dcmachine: 'M/G =',
  load3: 'Z',
  resistor: 'R',
  inductor: 'L',
  capacitor: 'C',
  ammeter: 'A',
  voltmeter: 'V',
  wattmeter: 'W',
}

function summary(type: string, p: Record<string, unknown>): string {
  switch (type) {
    case 'source3':
      return `${fmt(p.U_line)} V · ${fmt(p.f)} Hz`
    case 'source_dc':
      return `${fmt(p.U)} V`
    case 'switch3':
      return p.closed ? 'סגור' : 'פתוח'
    case 'load3':
      return `${String(p.kind)} · ${String(p.connection)} · ${fmt(p.value)}`
    case 'resistor':
      return `${fmt(p.R)} Ω`
    case 'inductor':
      return `${fmt(p.L)} H`
    case 'capacitor':
      return `${fmt(p.C)} F`
    case 'transformer3':
      return 'פרמטרים: מפרט השנאי'
    case 'syncmachine3':
      return `I_f = ${fmt(p.I_f ?? 0)} A`
    case 'woundmotor3':
      if (p.locked) return `נעול · α = ${fmt(p.angle ?? 0)}°`
      return p.speed_mode === 'speed' ? `n = ${fmt(p.n_set ?? 0)} rpm` : `M_load = ${fmt(p.M_load ?? 0)} N·m`
    case 'dcmachine':
      return p.speed_mode === 'speed' ? `n = ${fmt(p.n_set ?? 0)} rpm (סרוו)` : `בלם ${fmt(p.M_load ?? 0)} N·m`
    case 'motor3':
      return p.locked ? 'רוטור נעול' : `M_load = ${fmt(p.M_load ?? 0)} N·m`
    default:
      return ''
  }
}

export default function ComponentNode({ data, selected }: NodeProps<CompNode>) {
  const { comp, ctype } = data
  const terminals = ctype?.terminals ?? []
  const slots = terminalSlots(comp.type, terminals)
  const tall = comp.type === 'transformer3' || comp.type === 'motor3' || comp.type === 'syncmachine3' || comp.type === 'woundmotor3' || comp.type === 'dcmachine' ? 150 : comp.type === 'switch3' || comp.type === 'source3' || comp.type === 'load3' ? 110 : 70
  const wide = comp.type === 'transformer3' ? 180 : comp.type === 'motor3' || comp.type === 'syncmachine3' || comp.type === 'woundmotor3' || comp.type === 'dcmachine' ? 150 : 110
  const instrument = ctype?.instrument
  return (
    <div
      className={`sch-node${selected ? ' selected' : ''}${instrument ? ' instrument' : ''}${ctype ? '' : ' unknown'}`}
      style={{ width: wide, height: tall }}
      data-testid={`node-${comp.id}`}
      title={ctype?.label_he ?? comp.type}
    >
      <div className="sch-title">
        {comp.label && comp.label.startsWith(comp.id) ? (
          <strong>{comp.label}</strong>
        ) : (
          <>
            <strong>{comp.id}</strong> {comp.label && <span>{comp.label}</span>}
          </>
        )}
      </div>
      <div className="sch-symbol">{SYMBOL[comp.type] ?? '?'}</div>
      <div className="sch-sub">{summary(comp.type, comp.params)}</div>
      {terminals.map((t) => {
        const sl = slots[t] ?? { side: 'left', at: 0.5 }
        const style: React.CSSProperties =
          sl.side === 'left' || sl.side === 'right' ? { top: `${sl.at * 100}%` } : { left: `${sl.at * 100}%` }
        const labelStyle: React.CSSProperties =
          sl.side === 'left'
            ? { left: 6, top: `calc(${sl.at * 100}% - 8px)` }
            : sl.side === 'right'
              ? { right: 6, top: `calc(${sl.at * 100}% - 8px)` }
              : sl.side === 'bottom'
                ? { bottom: 4, left: `calc(${sl.at * 100}% - 10px)` }
                : { top: 4, left: `calc(${sl.at * 100}% - 10px)` }
        return (
          <span key={t}>
            <Handle
              id={t}
              type="source"
              position={POS[sl.side]}
              style={style}
              className="sch-handle"
              data-testid={`h-${comp.id}-${t}`}
            />
            <span className="sch-term" style={labelStyle}>
              {t}
            </span>
          </span>
        )
      })}
    </div>
  )
}
