import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MyModelsPage } from './MyModelsPage'

const model = {
  id: 5,
  name: 'wing.cas.h5',
  file_path: 'D:\\models\\wing.cas.h5',
  file_size: 1024,
  file_mtime: 'now',
  description: '',
  tags: [],
  automation_ids: [3],
  default_automation_id: 3,
  created_at: 'now',
  updated_at: 'now',
}

describe('MyModelsPage', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const open = vi.fn().mockResolvedValue({
      status: 'success',
      model_id: 5,
      message: 'Model loaded into Fluent.',
      connection: null,
    })
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({ state: 'ready' }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      models: {
        list: vi.fn().mockResolvedValue([model]),
        open,
        associate: vi.fn(),
        pickFile: vi.fn(),
        create: vi.fn(),
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('opens a solver model', async () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <MyModelsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByText('wing.cas.h5')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '打开' }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).models.open).toHaveBeenCalledWith(5, {
        load_case: true,
      })
    })
  })
})
