import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/renderer/src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    testTimeout: 20_000,
    hookTimeout: 20_000,
  },
})
