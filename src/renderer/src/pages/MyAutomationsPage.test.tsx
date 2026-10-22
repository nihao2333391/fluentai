import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MyAutomationsPage } from './MyAutomationsPage'

const model = {
  id: 8,
  name: 'recent.cas.h5',
  file_path: 'D:\\models\\recent.cas.h5',
  file_size: 100,
  file_mtime: 'now',
  description: '',
  tags: [],
  automation_ids: [4],
  default_automation_id: 4,
  created_at: 'now',
  updated_at: 'now',
}

const automation = {
  id: 4,
  name: 'Recent automation',
  description: '',
  status: 'active',
  preset: { schema_version: 1, fluent_version: '25.2.0', items: [] },
  created_at: 'now',
  updated_at: 'now',
}

describe('MyAutomationsPage recent session', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({ state: 'ready' }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      automations: { list: vi.fn().mockResolvedValue([automation]) },
      models: { list: vi.fn().mockResolvedValue([model]) },
      syncLogs: { list: vi.fn().mockResolvedValue([]) },
      session: {
        recent: vi.fn().mockResolvedValue({
          model,
          automation,
          meshing_automation: null,
          updated_at: '2026-10-22T00:00:00Z',
        }),
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('restores the last model and automation into the apply dialog', async () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <MyAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByText('上次会话')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '继续上次应用' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/应用自动化/)).toBeInTheDocument()
  })
})
