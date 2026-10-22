import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { AutomationCreatePage } from './AutomationCreatePage'

const catalog = [
  {
    setting_id: 'reference.area',
    display_name: 'Reference Area',
    group: 'reference',
    value_type: 'float',
    allowed_values: null,
    minimum: 0,
    maximum: null,
    description: 'Reference area',
  },
]

const automation = {
  id: 7,
  name: 'Existing automation',
  description: 'Existing description',
  status: 'active',
  preset: {
    schema_version: 1,
    fluent_version: '25.2.0',
    items: [
      {
        setting_id: 'reference.area',
        type: 'float',
        value: 1.25,
        required: true,
      },
    ],
  },
  created_at: 'now',
  updated_at: 'now',
}

describe('AutomationCreatePage edit mode', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const update = vi.fn().mockResolvedValue(automation)
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({ state: 'ready' }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      fluent: {
        catalog: vi.fn().mockResolvedValue(catalog),
        validatePreset: vi.fn().mockResolvedValue({
          valid: true,
          errors: [],
          normalized_items: automation.preset.items,
        }),
      },
      automations: {
        get: vi.fn().mockResolvedValue(automation),
        update,
        create: vi.fn(),
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('loads the persisted preset and saves updates', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/automations/7/edit']}>
          <AutomationCreatePage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByDisplayValue('Existing automation')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /保存修改/ }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).automations.update).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          name: 'Existing automation',
          description: 'Existing description',
          status: 'active',
        }),
      )
    })
  })
})
