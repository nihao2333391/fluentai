import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MeshingAutomationCreatePage } from './MeshingAutomationCreatePage'

const schema = {
  schema_version: 1,
  fluent_version: '25.2.0',
  workflow_type: 'watertight',
  display_name: 'Watertight Geometry',
  generated_at_utc: 'now',
  tasks: [
    {
      python_name: 'import_geometry',
      display_name: 'Import Geometry',
      command_name: 'ImportGeometry',
      task_type: 'Simple',
      check_point: 'default-off',
      state: 'Out-of-date',
      task_list: [],
      inactive_task_list: [],
      inactive_tasks: [],
      insertable_tasks: [],
      arguments: [
        {
          name: 'length_unit',
          edit_path: "workflow.task('import_geometry').command_arguments.length_unit",
          value_type: 'string',
          current_value: 'mm',
          allowed_values: ['m', 'cm', 'mm'],
          default_value: 'mm',
          read_only: false,
          editable: true,
          active: true,
          exposure_level: null,
          children: [],
        },
        {
          name: 'old_zone_list',
          edit_path: "workflow.task('import_geometry').command_arguments.old_zone_list",
          value_type: 'list',
          current_value: [],
          allowed_values: null,
          default_value: [],
          read_only: true,
          editable: false,
          active: true,
          exposure_level: null,
          children: [],
        },
      ],
      children: [],
    },
    {
      python_name: 'add_local_sizing',
      display_name: 'Add Local Sizing',
      command_name: 'AddLocalSizingWTM',
      task_type: 'Compound',
      check_point: 'default-off',
      state: 'Out-of-date',
      task_list: [],
      inactive_task_list: [],
      inactive_tasks: [],
      insertable_tasks: [],
      supports_child_template: true,
      child_template_warning: 'fallback',
      child_template: {
        python_name: '<compound-child-template>',
        display_name: 'Add Local Sizing Child',
        command_name: 'AddLocalSizingWTM',
        task_type: 'Compound Child',
        check_point: null,
        state: null,
        task_list: null,
        inactive_task_list: null,
        inactive_tasks: [],
        insertable_tasks: [],
        arguments: [
          {
            name: 'boi_control_name',
            edit_path: 'workflow.task("add_local_sizing").arguments.boi_control_name',
            value_type: 'string',
            current_value: 'facesize_1',
            allowed_values: null,
            default_value: 'facesize_1',
            read_only: false,
            editable: true,
            active: true,
            exposure_level: null,
            children: [],
          },
          {
            name: 'boi_face_label_list',
            edit_path: 'workflow.task("add_local_sizing").arguments.boi_face_label_list',
            value_type: 'list',
            current_value: [],
            allowed_values: null,
            default_value: [],
            read_only: false,
            editable: true,
            active: true,
            exposure_level: null,
            children: [],
          },
        ],
        children: [],
      },
      arguments: [],
      children: [],
    },
  ],
}

describe('MeshingAutomationCreatePage', () => {
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
      models: { list: vi.fn().mockResolvedValue([]) },
      meshing: {
        schema: vi.fn().mockResolvedValue(schema),
        validatePreset: vi.fn(),
      },
      meshingAutomations: { create: vi.fn() },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('renders the real task and typed option with advanced options collapsed', async () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <MeshingAutomationCreatePage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByText('Import Geometry')).toBeInTheDocument()
    expect(screen.getByText('length_unit')).toBeInTheDocument()
    expect(screen.getByText('高级与状态选项 (1)')).toBeInTheDocument()
    expect(screen.getByText('Watertight Geometry')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Add Local Sizing'))
    fireEvent.click(await screen.findByText('添加复合子任务预设'))
    expect(await screen.findByText('子任务/控制名称')).toBeInTheDocument()
    expect(screen.getByText('控制名称将自动写入 boi_control_name。')).toBeInTheDocument()
  })
})
