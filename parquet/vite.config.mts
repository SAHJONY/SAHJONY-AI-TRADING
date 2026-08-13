import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  root: resolve(here, 'ui'),
  publicDir: resolve(here, '../public'),
  plugins: [react()],
  build: {
    outDir: resolve(here, '../dist'), emptyOutDir: true,
    rolldownOptions: { output: { codeSplitting: { groups: [{ name: 'charts', test: /node_modules\/(recharts|d3-)/ }] } } },
  },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8788', '/ws': { target: 'ws://127.0.0.1:8788', ws: true } } },
})
