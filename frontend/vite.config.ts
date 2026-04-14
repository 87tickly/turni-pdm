import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8002',
      '/vt': 'http://localhost:8002',
      '/train': 'http://localhost:8002',
      '/station': 'http://localhost:8002',
      '/connections': 'http://localhost:8002',
      '/return-trains': 'http://localhost:8002',
      '/info': 'http://localhost:8002',
      '/constants': 'http://localhost:8002',
      '/validate-day': 'http://localhost:8002',
      '/build-auto': 'http://localhost:8002',
      '/save-shift': 'http://localhost:8002',
      '/saved-shifts': 'http://localhost:8002',
      '/upload': 'http://localhost:8002',
    },
  },
})
