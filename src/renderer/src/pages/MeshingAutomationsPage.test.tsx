import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

describe('MeshingAutomationsPage', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const apply = vi.fn().mockResolvedValue({
      status: 'success',
      automation_id: 11,
      model_id: 21,
      job_id: 'job-1',
      message: 'Meshing preset applied and verified before mesh generation.',
      connection: null,
      sync_log_id: 1,
      apply_report: {
        workflow_type: 'watertight',
        status: 'success',
        results: [{ success: true }],
        name_checks: [],
        created_children: [],
        stopped_before: ['Generate the Surface Mesh', 'Generate the Volume Mesh'],
        imported_model: model.file_path,
        missing_names: [],
        error: null,
      },
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
        apply,
        delete: vi.fn(),
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('applies a Meshing preset with the selected geometry model', async () => {
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
      expect((window.fluentAI as FluentAIApi).meshingAutomations.apply).toHaveBeenCalledWith(11, {
        model_id: 21,
        connection: null,
        import_geometry: true,
      })
    })
    expect(await screen.findByText('已写入并回读 1 项设置，未生成网格。')).toBeInTheDocument()
  })
})
