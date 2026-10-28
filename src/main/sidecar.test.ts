// @vitest-environment node

import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import type { Automation } from '../shared/contracts'
import { resolveSidecarDataDirectory, SidecarManager } from './sidecar'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

const resolvePython = (): string => {
  if (process.env.FLUENT_AI_PYTHON) {
    return process.env.FLUENT_AI_PYTHON
  }

  const windowsPython = join(appRoot, '.venv', 'Scripts', 'python.exe')
  if (existsSync(windowsPython)) {
    return windowsPython
  }

  return join(appRoot, '.venv', 'bin', 'python')
}

describe('SidecarManager', () => {
  it('uses an explicitly configured data directory when provided', () => {
    const userDataDirectory = join(tmpdir(), 'fluent-ai-user-data')
    const configuredDirectory = join(tmpdir(), 'fluent-ai-sidecar-data')

    expect(resolveSidecarDataDirectory(userDataDirectory, configuredDirectory)).toBe(
      resolve(configuredDirectory),
    )
  })

  it('keeps the default database under Electron user data when no override is set', () => {
    const userDataDirectory = join(tmpdir(), 'fluent-ai-user-data')

    expect(resolveSidecarDataDirectory(userDataDirectory, '')).toBe(
      join(userDataDirectory, 'data'),
    )
  })

  it('starts, reports an authenticated ready state, restarts, and stops', async () => {
    const dataDirectory = mkdtempSync(join(tmpdir(), 'fluent-ai-sidecar-'))
    const manager = new SidecarManager({
      appRoot,
      pythonExecutable: resolvePython(),
      dataDirectory,
      startTimeoutMs: 60_000,
    })
    const states: string[] = []
    const unsubscribe = manager.onStatusChanged((status) => {
      states.push(status.state)
    })

    try {
      const ready = await manager.start()

      expect(ready.state).toBe('ready')
      expect(ready.version).toBe('0.1.0')
      expect(ready.pid).toBeGreaterThan(0)
      expect(ready.port).toBeGreaterThan(0)
      expect(JSON.stringify(ready)).not.toContain('token')

      const initial = await manager.request<Automation[]>('/api/automations')
      expect(initial).toEqual([])
      const created = await manager.request<Automation>('/api/automations', {
        method: 'POST',
        body: JSON.stringify({
          name: 'Sidecar proxy automation',
          description: 'M4 request proxy',
          status: 'draft',
          preset: { schema_version: 1, fluent_version: null, items: [] },
        }),
      })
      expect(created.name).toBe('Sidecar proxy automation')

      const restarted = await manager.restart()
      expect(restarted.state).toBe('ready')
      expect(restarted.pid).toBeGreaterThan(0)
      expect(restarted.port).toBeGreaterThan(0)
      expect(states).toContain('starting')
      expect(states).toContain('ready')
      expect(states).toContain('stopped')
      const persisted = await manager.request<Automation[]>('/api/automations')
      expect(persisted.map((item) => item.name)).toContain('Sidecar proxy automation')
    } finally {
      unsubscribe()
      await manager.stop()
      rmSync(dataDirectory, { recursive: true, force: true })
    }

    expect(manager.getStatus().state).toBe('stopped')
  }, 90_000)
  it('automatically restarts after an unexpected sidecar exit', async () => {
    const dataDirectory = mkdtempSync(join(tmpdir(), 'fluent-ai-sidecar-restart-'))
    const manager = new SidecarManager({
      appRoot,
      pythonExecutable: resolvePython(),
      dataDirectory,
      startTimeoutMs: 20_000,
      maxAutoRestarts: 1,
    })

    try {
      const firstReady = await manager.start()
      expect(firstReady.state).toBe('ready')
      expect(firstReady.pid).toBeGreaterThan(0)

      process.kill(firstReady.pid as number, 'SIGTERM')

      const deadline = Date.now() + 20_000
      while (Date.now() < deadline) {
        const status = manager.getStatus()
        if (status.state === 'ready' && status.pid !== firstReady.pid) {
          break
        }
        await new Promise((resolve) => setTimeout(resolve, 200))
      }

      const restarted = manager.getStatus()
      expect(restarted.state).toBe('ready')
      expect(restarted.pid).not.toBe(firstReady.pid)
    } finally {
      await manager.stop()
      rmSync(dataDirectory, { recursive: true, force: true })
    }
  }, 45_000)
})
