import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  FluentAIApi,
  MeshingLiveSessionSnapshot,
  MeshingSchemaTask,
  MeshingWorkflowSchema,
} from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useAppStore } from '../store/appStore'
import { MeshingLiveSyncPage } from './MeshingLiveSyncPage'

const task = (pythonName: string, displayName: string): MeshingSchemaTask => ({
  python_name: pythonName,
  display_name: displayName,
  command_name: displayName,
  task_type: 'Simple',
  check_point: '',
  state: '',
  task_list: [],
  inactive_task_list: [],
  inactive_tasks: [],
  insertable_tasks: [],
  arguments: [],
  children: [],
})

const localSizingTask = {
  ...task('add_local_sizing', 'Add Local Sizing'),
  task_type: 'Compound' as const,
  arguments: [
    {
      name: 'add_child',
      display_name: 'Would you like to add local sizing?',
      edit_path: 'add_child',
      value_type: 'string',
      current_value: 'yes',
      allowed_values: ['yes', 'no'],
      default_value: 'yes',
      read_only: false,
      active: true,
      exposure_level: null,
      children: [],
    },
  ],
  child_template: {
    ...task('<child>', 'Child'),
    arguments: [
      {
        name: 'boi_size',
        display_name: 'Target Mesh Size',
        edit_path: 'boi_size',
        value_type: 'float',
        current_value: 0.002,
        allowed_values: null,
        default_value: 0.002,
        read_only: false,
        active: true,
        exposure_level: null,
        children: [],
      },
    ],
  },
  supports_child_template: true,
}

const schema: MeshingWorkflowSchema = {
  schema_version: 1,
  fluent_version: '25.2.0',
  workflow_type: 'watertight',
  generated_at_utc: 'now',
  tasks: [
    task('import_geometry', 'Import Geometry'),
    localSizingTask,
    task('create_surface_mesh', 'Generate the Surface Mesh'),
    task('describe_geometry', 'Describe Geometry'),
    task('update_regions', 'Update Regions'),
    task('add_boundary_layer', 'Add Boundary Layers'),
    task('create_volume_mesh', 'Generate the Volume Mesh'),
  ],
}

const snapshot: MeshingLiveSessionSnapshot = {
  session_id: 'session-1',
  automation_id: 11,
  automation_name: 'Live Venturi',
  workflow_type: 'watertight',
  status: 'waiting',
  connection: {
    connected: true,
    mode: 'launch',
    version: '25.2.0',
    pid: 1,
    host: 'local',
    port: 1,
  },
  models: [
    {
      model_id: 21,
      name: 'venturi.dsco',
      file_path: 'D:\\models\\venturi.dsco',
      status: 'ready',
      error: null,
    },
  ],
  current_model_index: 0,
  current_step_index: 1,
  steps: [
    { task_path: ['import_geometry'], status: 'completed', message: '' },
    { task_path: ['add_local_sizing'], status: 'active', message: '' },
    { task_path: ['create_surface_mesh'], status: 'pending', message: '' },
    { task_path: ['describe_geometry'], status: 'pending', message: '' },
    { task_path: ['update_regions'], status: 'pending', message: '' },
    { task_path: ['add_boundary_layer'], status: 'pending', message: '' },
    { task_path: ['create_volume_mesh'], status: 'pending', message: '' },
  ],
  logs: [],
  message: '',
}

const stepReport = {
  status: 'success' as const,
  message: '',
  snapshot,
  step_index: 1,
  task_path: ['add_local_sizing'],
  write_report: null,
  read_report: {
    workflow_type: 'watertight' as const,
    status: 'success' as const,
    task_names: [],
    error: null,
    items: [
      {
        task_path: ['add_local_sizing'],
        argument_path: ['add_child'],
        compound_child_name: null,
        found: true,
        value: 'yes',
        error: null,
      },
      {
        task_path: ['add_local_sizing'],
        argument_path: ['boi_size'],
        compound_child_name: 'facesize_1',
        found: true,
        value: 0.002,
        error: null,
      },
    ],
  },
}

describe('MeshingLiveSyncPage', () => {
  beforeEach(() => {
    useAppStore.setState({ themeMode: 'system', language: 'zh' })
    const api = {
      meshingAutomations: {
        get: vi.fn().mockResolvedValue({
          id: 11,
          name: 'Live Venturi',
          description: '',
          model_family: 'Venturi',
          reference_model_id: 21,
          status: 'active',
          created_at: 'now',
          updated_at: 'now',
          preset: {
            schema_version: 1,
            fluent_version: '25.2.0',
            workflow_type: 'watertight',
            items: [],
          },
        }),
      },
      meshing: { schema: vi.fn().mockResolvedValue(schema) },
      meshingLive: {
        get: vi.fn().mockResolvedValue(snapshot),
        enterStep: vi.fn().mockResolvedValue(stepReport),
        readStep: vi.fn().mockResolvedValue(stepReport),
        writeStep: vi.fn().mockResolvedValue(stepReport),
        executeStep: vi.fn().mockResolvedValue(stepReport),
        nextModel: vi.fn().mockResolvedValue(snapshot),
        retryModel: vi.fn().mockResolvedValue(snapshot),
        stop: vi.fn().mockResolvedValue(snapshot),
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('enters the current step, shows readback values, and executes the task', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing/live/session-1']}>
          <Routes>
            <Route path="/meshing/live/:sessionId" element={<MeshingLiveSyncPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByText('Live Venturi')).toBeInTheDocument()
    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).meshingLive.enterStep).toHaveBeenCalledWith(
        'session-1',
        { step_index: 1 },
      )
    })
    expect(await screen.findByText('目标网格尺寸')).toBeInTheDocument()
    const sizeInput = screen.getByRole('spinbutton')
    expect(sizeInput).toHaveValue('0.0020')

    fireEvent.change(sizeInput, { target: { value: '0.003' } })
    await waitFor(
      () => {
        expect((window.fluentAI as FluentAIApi).meshingLive.writeStep).toHaveBeenCalledWith(
          'session-1',
          expect.objectContaining({
            step_index: 1,
            items: expect.arrayContaining([
              expect.objectContaining({
                argument_path: ['boi_size'],
                value: 0.003,
                compound_child_name: 'facesize_1',
              }),
            ]),
          }),
        )
      },
      { timeout: 2000 },
    )

    fireEvent.click(screen.getByRole('button', { name: /执行.*添加局部尺寸/ }))
    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).meshingLive.executeStep).toHaveBeenCalledWith(
        'session-1',
        { step_index: 1 },
      )
    })
  })

  it('marks values changed in Fluent Meshing as external', async () => {
    const api = window.fluentAI as FluentAIApi
    const changedReport = {
      ...stepReport,
      read_report: {
        ...stepReport.read_report,
        items: stepReport.read_report.items.map((item) =>
          item.argument_path[0] === 'boi_size' ? { ...item, value: 0.006 } : item,
        ),
      },
    }
    vi.mocked(api.meshingLive.readStep)
      .mockResolvedValueOnce(stepReport)
      .mockResolvedValueOnce(changedReport)

    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing/live/session-1']}>
          <Routes>
            <Route path="/meshing/live/:sessionId" element={<MeshingLiveSyncPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    )

    expect(
      await screen.findByText('参数已在 Fluent Meshing 中被修改', {}, { timeout: 5500 }),
    ).toBeInTheDocument()
    expect(screen.getByText('外部已修改')).toBeInTheDocument()
  }, 10_000)
})
