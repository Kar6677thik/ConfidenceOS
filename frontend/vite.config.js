import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'happy-dom',
    setupFiles: ['./src/test/setup.js'],
    globals: true,
  },
  server: {
    port: 5174,
    allowedHosts: ['confidence.karthiksurkanti.in'],
    proxy: {
      '/ws': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
        timeout: 30000,
        proxyTimeout: 30000,
      },
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        timeout: 30000,
        proxyTimeout: 30000,
      },
    },
  },
})
