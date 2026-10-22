import { describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { fluentAiService, getFluentAIApi } from './fluentAi'

describe('fluentAiService', () => {
  it('delegates business operations through the preload API', async () => {
    const automation = {
      id: 1,
      name: 'Baseline',
      description: '',
      status: 'draft' as const,
      preset: { schema_version: 1 as const, fluent_version: null, items: [] },
      created_at: 'now',
      updated_at: 'now',
    }
    const api = {
      platform: 'win32',
      sidecar: {
        getStatus: vi.fn(),
        restart: vi.fn(),
        onStatusChanged: vi.fn(),
      },
      automations: {
        list: vi.fn().mockResolvedValue([automation]),
        create: vi.fn().mockResolvedValue(automation),
        get: vi.fn().mockResolvedValue(automation),
        update: vi.fn().mockResolvedValue(automation),
        delete: vi.fn().mockResolvedValue(undefined),
      },
      models: {
        list: vi.fn(),
        get: vi.fn(),
        pickFile: vi.fn(),
        create: vi.fn(),
        update: vi.fn(),
        associate: vi.fn(),
        open: vi.fn(),
        refresh: vi.fn(),
        delete: vi.fn(),
      },
      settings: { get: vi.fn(), update: vi.fn() },
      jobs: { list: vi.fn(), get: vi.fn() },
      syncLogs: { list: vi.fn() },
      credentials: {
        getStatus: vi.fn(),
        setFluentPassword: vi.fn(),
        clearFluentPassword: vi.fn(),
      },
      fluent: {
        status: vi.fn(),
        connect: vi.fn(),
        disconnect: vi.fn(),
        catalog: vi.fn(),
        readSettings: vi.fn(),
        writeSettings: vi.fn(),
        validatePreset: vi.fn(),
        applyPreset: vi.fn(),
      },
      workflows: {
        applyAutomation: vi.fn(),
      },
      meshing: {
        schemas: vi.fn().mockResolvedValue([]),
        schema: vi.fn().mockResolvedValue({ tasks: [] }),
        validatePreset: vi.fn().mockResolvedValue({
          valid: true,
          errors: [],
          schema_id: 'fluent-meshing-25.2-watertight',
          item_count: 0,
        }),
      },
      meshingAutomations: {
        list: vi.fn().mockResolvedValue([]),
        create: vi.fn(),
        get: vi.fn(),
        update: vi.fn(),
        delete: vi.fn(),
        validate: vi.fn(),
        apply: vi.fn(),
      },
    } satisfies FluentAIApi

    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })

    await expect(fluentAiService.automations.list()).resolves.toEqual([automation])
    expect(getFluentAIApi()).toBe(api)
  })

  it('throws when the preload API is unavailable', () => {
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: undefined })
    expect(() => getFluentAIApi()).toThrow(/preload API is unavailable/)
  })
})
