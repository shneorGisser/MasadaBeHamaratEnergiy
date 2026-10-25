/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { pyodideAssets } from './vite-plugins/pyodide-assets.ts'

const backend = process.env.VEL_BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), pyodideAssets()],
  server: { proxy: { '/api': backend } },
  build: { chunkSizeWarningLimit: 2000 },
  worker: { format: 'es' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
