import { describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { fluentAiService, getFluentAIApi } from './fluentAi'

describe('fluentAiService', () => {
  it('delegates business operations through the preload API', async () => {
    const model = {
      id: 1,
      name: 'baseline.cas.h5',
      file_path: 'D:\\models\\baseline.cas.h5',
      file_size: 1024,
      file_mtime: 'now',
      description: '',
      tags: [],
      automation_ids: [],
      default_automation_id: null,
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
      models: {
        list: vi.fn().mockResolvedValue([model]),
        get: vi.fn(),
        pickFile: vi.fn(),
        create: vi.fn(),
        update: vi.fn(),
        open: vi.fn(),
        refresh: vi.fn(),
        delete: vi.fn(),
      },
      settings: { get: vi.fn(), update: vi.fn() },
      jobs: { list: vi.fn(), get: vi.fn(), cancel: vi.fn() },
      syncLogs: { list: vi.fn() },
      system: {
        listBackups: vi.fn(),
        createBackup: vi.fn(),
        restoreBackup: vi.fn(),
      },
      credentials: {
        getStatus: vi.fn(),
        setFluentPassword: vi.fn(),
        clearFluentPassword: vi.fn(),
        getAgentApiKeyStatus: vi.fn(),
        setAgentApiKey: vi.fn(),
        clearAgentApiKey: vi.fn(),
      },
      agent: {
        getModelConfig: vi.fn(),
        saveModelConfig: vi.fn(),
        testModel: vi.fn(),
        testCapabilities: vi.fn(),
        getSession: vi.fn(),
        getProactiveSuggestion: vi.fn(),
        sendMessage: vi.fn(),
        onEvent: vi.fn(),
        stopMessage: vi.fn(),
        getCategoryCapabilities: vi.fn().mockResolvedValue({
          category_id: 'uncategorized',
          knowledge: [],
          rules: [],
          tools: [],
        }),
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
      meshing: {
        status: vi.fn(),
        connect: vi.fn(),
        disconnect: vi.fn(),
        read: vi.fn(),
        write: vi.fn(),
        workflowSchema: vi.fn(),
        schemas: vi.fn().mockResolvedValue([]),
        schema: vi.fn().mockResolvedValue({ tasks: [] }),
        validatePreset: vi.fn().mockResolvedValue({
          valid: true,
          errors: [],
          schema_id: 'fluent-meshing-25.2-watertight',
          item_count: 0,
        }),
        inspectReferenceModel: vi.fn(),
      },
      meshingAutomations: {
        list: vi.fn().mockResolvedValue([]),
        create: vi.fn(),
        get: vi.fn(),
        update: vi.fn(),
        delete: vi.fn(),
        validate: vi.fn(),
        publish: vi.fn(),
      },
      meshingLive: {
        start: vi.fn(),
        get: vi.fn(),
        enterStep: vi.fn(),
        readStep: vi.fn(),
        writeStep: vi.fn(),
        executeStep: vi.fn(),
        retryPrepare: vi.fn(),
        nextModel: vi.fn(),
        retryModel: vi.fn(),
        stop: vi.fn(),
        pickMeshFile: vi.fn(),
        archive: vi.fn(),
        archives: vi.fn().mockResolvedValue([]),
      },
      categories: {
        list: vi.fn().mockResolvedValue([]),
        create: vi.fn(),
        rename: vi.fn(),
        delete: vi.fn(),
      },
      meshingTasks: {
        list: vi.fn().mockResolvedValue([]),
        history: vi.fn(),
        delete: vi.fn(),
      },
    } satisfies FluentAIApi

    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })

    await expect(fluentAiService.models.list()).resolves.toEqual([model])
    expect(getFluentAIApi()).toBe(api)
  })

  it('throws when the preload API is unavailable', () => {
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: undefined })
    expect(() => getFluentAIApi()).toThrow(/preload API is unavailable/)
  })
})
