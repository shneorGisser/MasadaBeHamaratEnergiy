/// <reference lib="webworker" />
/** ngspice runs here, off the UI thread: a transient of tens of thousands of steps would freeze
 * the page otherwise. The engine (~20 MB) is fetched on the first run only. */
import { TOPOLOGIES, type Mode, type P } from './circuits'
import { decimate } from './analyse'
import { runTopology } from './run'

export interface RunRequest {
  id: number
  topology: string
  params: P
  mode: Mode
}

self.onmessage = async (ev: MessageEvent<RunRequest>) => {
  const { id, topology, params, mode } = ev.data
  try {
    const t = TOPOLOGIES.find((x) => x.id === topology)
    if (!t) throw new Error(`unknown topology ${topology}`)
    const r = await runTopology(t, params, mode)
    // the charts show the analysis window (steady state); the start-up is in the netlist run
    const [t0, t1] = r.window
    const traces = Object.fromEntries(
      Object.entries(r.traces).map(([k, v]) => [k, decimate(v.filter((q) => q[0] >= t0 && q[0] <= t1), 2000)]),
    )
    self.postMessage({ id, ok: true, result: { ...r, traces } })
  } catch (e) {
    self.postMessage({ id, ok: false, error: e instanceof Error ? e.message : String(e) })
  }
}
