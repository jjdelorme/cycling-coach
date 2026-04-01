import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'
import path from 'path'
import { execSync } from 'child_process'

const versionFile = path.resolve(__dirname, '..', 'VERSION')
let version = 'development'

if (fs.existsSync(versionFile)) {
  version = fs.readFileSync(versionFile, 'utf-8').trim()
} else {
  try {
    version = execSync('git describe --tags --always').toString().trim().replace(/^v/, '')
  } catch (e) {
    console.warn('Could not determine version from git, falling back to "development"')
  }
}

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
