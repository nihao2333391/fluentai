import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MeshingAutomationsPage } from './MeshingAutomationsPage'

const automation = {
  id: 11,
  name: 'Venturi Meshing',
  description: 'Reference preset',
  model_family: 'Venturi',
  reference_model_id: 21,
  preset: {
    schema_version: 1,
    fluent_version: '25.2.0',
    workflow_type: 'watertight',
    items: [],
  },
  status: 'draft',
  created_at: 'now',
  updated_at: 'now',
}

const model = {
  id: 21,
  name: 'venturi.dsco.pmdb',
  file_path: 'D:\\models\\venturi.dsco.pmdb',
  file_size: 100,
  file_mtime: 'now',
  description: '',
  tags: [],
  automation_ids: [],
  default_automation_id: null,
  created_at: 'now',
  updated_at: 'now',
}

const LocationProbe = () => {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

describe('MeshingAutomationsPage', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const start = vi.fn().mockResolvedValue({
      session_id: 'session-1',
      automation_id: 11,
      automation_name: automation.name,
      workflow_type: 'watertight',
      status: 'waiting',
      connection: null,
      models: [],
      current_model_index: 0,
      current_step_index: 1,
      steps: [],
      logs: [],
      message: '',
    })
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({ state: 'ready' }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      models: { list: vi.fn().mockResolvedValue([model]) },
      meshingAutomations: {
        list: vi.fn().mockResolvedValue([automation]),
        delete: vi.fn(),
      },
      meshingLive: { start },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('starts a live Meshing session with the selected geometry model', async () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <MeshingAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByText('Venturi Meshing')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '应用' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /应\s*用/ }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).meshingLive.start).toHaveBeenCalledWith({
        automation_id: 11,
        model_ids: [21],
        connection: null,
      })
    })
  })

  it('opens the existing Meshing preset in the editor', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing']}>
          <MeshingAutomationsPage />
          <LocationProbe />
        </MemoryRouter>
      </AppProviders>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '编辑' }))

    expect(screen.getByTestId('location')).toHaveTextContent('/meshing/11/edit')
  })
})
