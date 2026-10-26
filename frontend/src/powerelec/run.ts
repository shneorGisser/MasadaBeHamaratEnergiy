/** Run one topology in ngspice (eecircuit-engine) and analyse it. Works in a Web Worker and in
 * Node (the tests). The engine module (~20 MB, the WASM inside) is loaded on first use. */
import { probeTraces, signals, type RawResult } from './analyse'
import type { Check, Mode, P, Topology } from './circuits'
import type { XY } from '../components/scope'

type Sim = {
  start(): Promise<void>
  setNetList(n: string): void
  runSim(): Promise<RawResult>
  getError(): string[]
  getInfo(): string
}
let simP: Promise<Sim> | null = null

async function engine(): Promise<Sim> {
  if (!simP) {
    simP = (async () => {
      const { Simulation } = await import('eecircuit-engine')
      const s = new Simulation() as unknown as Sim
      await s.start()
      return s
    })()
  }
  return simP
}

export interface BenchResult {
  traces: Record<string, XY>
  checks: Check[]
  window: [number, number]
  netlist: string
  ms: number
  points: number
}

export async function runTopology(t: Topology, p: P, mode: Mode): Promise<BenchResult> {
  const sim = await engine()
  const netlist = t.netlist(p, mode)
  const t0 = performance.now()
  sim.setNetList(netlist)
  const raw = await sim.runSim()
  const errs = sim.getError().filter((e) => /error/i.test(e))
  if (errs.length) throw new Error(`ngspice: ${errs.join('; ')}`)
  const tm = t.timing(p)
  const time = raw.data.find((d) => d.name.toLowerCase() === 'time')?.values
  const reached = time && time.length ? time[time.length - 1]! : 0
  if (reached < 0.999 * tm.tstop) {
    // a failed transient is a failure, never a short result
    const why = /Timestep too small[^\n]*/.exec(sim.getInfo())?.[0] ?? 'ngspice stopped early'
    throw new Error(`הסימולציה נעצרה ב-t = ${(reached * 1e3).toFixed(2)} ms מתוך ${(tm.tstop * 1e3).toFixed(2)} ms: ${why}`)
  }
  const traces = probeTraces(t, raw)
  const window: [number, number] = [tm.t0, tm.t1]
  const checks = t.checks(p, signals(traces, window))
  const points = Object.values(traces)[0]?.length ?? 0
  return { traces, checks, window, netlist, ms: performance.now() - t0, points }
}
