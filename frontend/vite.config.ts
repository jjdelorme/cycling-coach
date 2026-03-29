import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { execSync } from 'child_process'
import fs from 'fs'
import path from 'path'

function getVersion(): string {
  const versionFile = path.resolve(__dirname, '..', 'VERSION')
  if (fs.existsSync(versionFile)) {
    return fs.readFileSync(versionFile, 'utf-8').trim()
  }
  try {
    return execSync('git describe --tags --always', { cwd: __dirname })
      .toString().trim().replace(/^v/, '')
  } catch {
    return 'dev'
  }
}
const version = getVersion()

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
