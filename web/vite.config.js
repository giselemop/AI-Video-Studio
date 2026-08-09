import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    host: '127.0.0.1',
    port: 18081,
    proxy: { '/api': 'http://127.0.0.1:18080', '/media': 'http://127.0.0.1:18080' }
  },
  build: { outDir: 'dist', emptyOutDir: true }
})
