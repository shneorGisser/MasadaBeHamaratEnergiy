/// <reference lib="webworker" />
/**
 * Runs a user script in Pyodide, off the main thread (a long script never freezes the page,
 * and "stop" simply terminates the worker). Pyodide is served from our own origin
 * (/pyodide/, copied from the npm package at build time) — no CDN, works in a closed lab.
 */
import prelude from './prelude.py?raw'

export type ToWorker = { type: 'run'; code: string; projectId: string }
export type FromWorker =
  | { type: 'status'; text: string }
  | { type: 'stdout'; text: string }
  | { type: 'stderr'; text: string }
  | { type: 'plot'; spec: string }
  | { type: 'done'; ms: number }
  | { type: 'error'; text: string }

interface Pyodide {
  setStdout(o: { batched: (s: string) => void }): void
  setStderr(o: { batched: (s: string) => void }): void
  registerJsModule(name: string, mod: object): void
  runPythonAsync(code: string): Promise<unknown>
}

let py: Pyodide | null = null
let projectId = ''
const post = (m: FromWorker) => (self as unknown as Worker).postMessage(m)

async function http(method: string, path: string, body?: string): Promise<string> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body,
  })
  const text = await res.text()
  if (!res.ok && res.status !== 201) {
    let msg = `${res.status}`
    try {
      msg = JSON.parse(text)?.error?.message ?? msg
    } catch {
      /* keep the status */
    }
    throw new Error(`HTTP ${msg}`)
  }
  return text
}

async function boot(): Promise<Pyodide> {
  if (py) return py
  post({ type: 'status', text: 'טוען את Python (Pyodide)…' })
  const url = new URL('/pyodide/pyodide.mjs', self.location.origin).href
  const mod = (await import(/* @vite-ignore */ url)) as {
    loadPyodide: (o: { indexURL: string }) => Promise<Pyodide>
  }
  const p = await mod.loadPyodide({ indexURL: new URL('/pyodide/', self.location.origin).href })
  p.setStdout({ batched: (s) => post({ type: 'stdout', text: s }) })
  p.setStderr({ batched: (s) => post({ type: 'stderr', text: s }) })
  p.registerJsModule('_vlab_js', {
    studies: () => http('GET', `/api/projects/${projectId}/studies`),
    spec: async () => JSON.stringify(JSON.parse(await http('GET', `/api/projects/${projectId}`)).spec),
    run: (study: string, caseJson: string, label: string) =>
      http(
        'POST',
        `/api/projects/${projectId}/runs`,
        JSON.stringify({ study_kind: study, case: JSON.parse(caseJson), label: `script: ${label}`.slice(0, 200) }),
      ),
    plot: (spec: string) => post({ type: 'plot', spec }),
  })
  await p.runPythonAsync(
    `import sys, types\nvlab = types.ModuleType("vlab")\nexec(${JSON.stringify(prelude)}, vlab.__dict__)\nsys.modules["vlab"] = vlab`,
  )
  py = p
  return p
}

self.onmessage = async (ev: MessageEvent<ToWorker>) => {
  const m = ev.data
  if (m.type !== 'run') return
  projectId = m.projectId
  const t0 = performance.now()
  try {
    const p = await boot()
    post({ type: 'status', text: 'מריץ…' })
    await p.runPythonAsync(m.code)
    post({ type: 'done', ms: performance.now() - t0 })
  } catch (e) {
    const text = e instanceof Error ? e.message : String(e)
    // keep the user's part of a Python traceback: drop Pyodide's internal frames
    const lines = text.split('\n')
    const start = lines.findIndex((l) => l.includes('File "<exec>"'))
    post({ type: 'error', text: start > 0 ? ['Traceback:', ...lines.slice(start)].join('\n') : text })
  }
}
