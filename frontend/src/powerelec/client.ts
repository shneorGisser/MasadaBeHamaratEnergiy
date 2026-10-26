/** Promise wrapper around the bench's Web Worker. */
import type { Mode, P } from './circuits'
import type { BenchResult } from './run'

let worker: Worker | null = null
let seq = 0
const pending = new Map<number, { resolve: (r: BenchResult) => void; reject: (e: Error) => void }>()

function get(): Worker {
  if (!worker) {
    worker = new Worker(new URL('./pe.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (ev: MessageEvent<{ id: number; ok: boolean; result?: BenchResult; error?: string }>) => {
      const p = pending.get(ev.data.id)
      if (!p) return
      pending.delete(ev.data.id)
      if (ev.data.ok && ev.data.result) p.resolve(ev.data.result)
      else p.reject(new Error(ev.data.error ?? 'simulation failed'))
    }
    worker.onerror = (ev) => {
      for (const p of pending.values()) p.reject(new Error(ev.message || 'worker error'))
      pending.clear()
      worker = null
    }
  }
  return worker
}

export function simulate(topology: string, params: P, mode: Mode): Promise<BenchResult> {
  const id = ++seq
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    get().postMessage({ id, topology, params, mode })
  })
}
