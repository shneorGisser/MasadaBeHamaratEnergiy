import { copyFileSync, createReadStream, existsSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

/** Files of the pyodide npm package the browser loads (the rest are Node-only or typings). */
const FILES = ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']
const TYPES: Record<string, string> = {
  mjs: 'text/javascript',
  wasm: 'application/wasm',
  zip: 'application/zip',
  json: 'application/json',
}

/** Serve /pyodide/* from node_modules in dev, copy it to dist/pyodide on build. */
export function pyodideAssets(): Plugin {
  const src = fileURLToPath(new URL('../node_modules/pyodide', import.meta.url))
  return {
    name: 'vel-pyodide-assets',
    configureServer(server) {
      server.middlewares.use('/pyodide', (req, res, next) => {
        const name = (req.url ?? '').replace(/^\//, '').split('?')[0] ?? ''
        if (!FILES.includes(name)) return next()
        res.setHeader('Content-Type', TYPES[name.split('.').pop() ?? ''] ?? 'application/octet-stream')
        createReadStream(resolve(src, name)).pipe(res)
      })
    },
    writeBundle(opts) {
      const out = resolve(opts.dir ?? 'dist', 'pyodide')
      mkdirSync(out, { recursive: true })
      for (const f of FILES) {
        const from = resolve(src, f)
        if (!existsSync(from)) throw new Error(`pyodide asset missing: ${from}`)
        copyFileSync(from, resolve(out, f))
      }
    },
  }
}
