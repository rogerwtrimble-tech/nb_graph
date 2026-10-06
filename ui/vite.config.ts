import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In docker the UI is served by nginx, which proxies /api to graph-api.
// In `npm run dev` Vite does the same proxying (point GRAPH_API at your graph-api).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.GRAPH_API ?? 'http://localhost:8090', changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 2000 },
})
