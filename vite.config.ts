import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import compression from 'vite-plugin-compression'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // Pre-compress JS/CSS assets at build time. Nginx can serve the .br /
    // .gz files directly when the client supports them, halving bytes on
    // the wire for the leaflet/georaster vendor chunk in particular.
    compression({ algorithm: 'brotliCompress', ext: '.br', threshold: 1024 }),
    compression({ algorithm: 'gzip', ext: '.gz', threshold: 1024 }),
  ],
  server: {
    proxy: {
      '/predict': 'http://localhost:8080/',
      '/status': 'http://localhost:8080/',
      '/result': 'http://localhost:8080/',
      '/events': {
        target: 'http://localhost:8080/',
        headers: { 'X-Accel-Buffering': 'no' },
      },
      '/api': 'http://localhost:8080/',
    },
  },
  build: {
    outDir: 'app/ui',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'pinia'],
          'vendor-leaflet': ['leaflet', 'georaster', 'georaster-layer-for-leaflet'],
          'vendor-bootstrap': ['bootstrap'],
        },
      },
    },
  },
})
