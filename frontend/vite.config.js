import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The browser only talks to its own origin: Vite forwards /api to the local FastAPI server
// (run from api/: uvicorn app.main:create_app --factory --reload), so the backend needs no CORS.
const apiTarget = process.env.PULSE_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
  },
})
