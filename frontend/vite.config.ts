import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // aladin-lite (WASM, ~2.4 MB) is lazy-loaded as its own chunk; the main bundle stays small.
  build: { chunkSizeWarningLimit: 2600 },
  server: {
    // Same-origin in dev: the backend runs on :8000 (see CLAUDE.md → Commands).
    proxy: {
      '/api': 'http://localhost:8000',
      '/files': 'http://localhost:8000',
    },
  },
})
