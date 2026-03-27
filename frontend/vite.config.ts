import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'
import path from 'path'

const version = fs.readFileSync(path.resolve(__dirname, '..', 'VERSION'), 'utf-8').trim()

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: '..',
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
