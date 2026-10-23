import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../shared/contracts'
import App from './App'
import { useAppStore } from './store/appStore'

const createMockApi = (): FluentAIApi => ({
  platform: 'win32',
  sidecar: {
    getStatus: vi.fn().mockResolvedValue({
      state: 'ready',
      message: 'Sidecar ready',
      version: '0.1.0',
      pid: 4321,
      port: 61234,
    }),
    restart: vi.fn().mockResolvedValue({
      state: 'ready',
      message: 'Sidecar ready',
      version: '0.1.0',
      pid: 4322,
      port: 61235,
    }),
    onStatusChanged: vi.fn(() => () => undefined),
  },
  automations: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  models: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
    pickFile: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    associate: vi.fn(),
    open: vi.fn(),
    refresh: vi.fn(),
    delete: vi.fn(),
  },
  settings: {
    get: vi.fn().mockResolvedValue({ values: {} }),
    update: vi.fn(),
  },
  jobs: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
    cancel: vi.fn(),
  },
  syncLogs: {
    list: vi.fn().mockResolvedValue([]),
  },
  session: {
    recent: vi.fn().mockResolvedValue({
      model: null,
      automation: null,
      meshing_automation: null,
      updated_at: null,
    }),
  },
  system: {
    listBackups: vi.fn().mockResolvedValue({ backups: [] }),
    createBackup: vi.fn(),
    restoreBackup: vi.fn(),
  },
  credentials: {
    getStatus: vi.fn().mockResolvedValue({ encryptionAvailable: true, configured: false }),
    setFluentPassword: vi.fn(),
    clearFluentPassword: vi.fn(),
  },
  fluent: {
    status: vi.fn().mockResolvedValue({
      connected: false,
      mode: null,
      version: null,
      pid: null,
      host: null,
      port: null,
    }),
    connect: vi.fn(),
    disconnect: vi.fn(),
    catalog: vi.fn().mockResolvedValue([
      {
        setting_id: 'residual.continuity',
        display_name: 'Residual criterion: continuity',
        group: 'solution',
        value_type: 'float',
        allowed_values: null,
        minimum: 1e-12,
        maximum: 1,
        description: 'Continuity residual',
      },
    ]),
    readSettings: vi.fn(),
    writeSettings: vi.fn(),
    validatePreset: vi.fn().mockResolvedValue({ valid: true, errors: [], normalized_items: [] }),
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
})

describe('App', () => {
  beforeEach(() => {
    localStorage.clear()
    useAppStore.setState({ themeMode: 'system', language: 'zh' })
    window.location.hash = '#/automations/create'
    Object.defineProperty(window, 'fluentAI', {
      configurable: true,
      value: createMockApi(),
    })
  })

  it('renders the four-module shell and navigates between routes', async () => {
    render(<App />)

    expect(await screen.findByRole('heading', { name: '自动化创建' })).toBeInTheDocument()
    expect(await screen.findByText('Fluent 工作流预设')).toBeInTheDocument()
    expect(screen.getByText('常规')).toBeInTheDocument()
    expect(screen.getByText('模型')).toBeInTheDocument()
    expect(screen.getByText('求解')).toBeInTheDocument()
    expect(screen.getByText('参考值')).toBeInTheDocument()
    expect(screen.getByText('我的自动化')).toBeInTheDocument()
    expect(screen.getByText('我的模型')).toBeInTheDocument()
    expect(screen.getByText('设置')).toBeInTheDocument()

    fireEvent.click(screen.getByText('我的模型'))
    expect(await screen.findByRole('heading', { name: '我的模型' })).toBeInTheDocument()

    fireEvent.click(screen.getByText('设置'))
    expect(await screen.findByText('界面外观')).toBeInTheDocument()
  })

  it('switches theme and language immediately', async () => {
    render(<App />)

    fireEvent.click(await screen.findByText('设置'))
    fireEvent.click(await screen.findByText('深色'))
    expect(document.documentElement.dataset.theme).toBe('dark')

    act(() => {
      useAppStore.getState().setLanguage('en')
    })

    expect(await screen.findByText('Appearance')).toBeInTheDocument()
    expect(screen.getByText('Create Automation')).toBeInTheDocument()
  })
})
