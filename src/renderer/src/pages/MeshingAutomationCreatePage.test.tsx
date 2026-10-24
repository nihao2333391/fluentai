import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  FluentAIApi,
  MeshingSchemaArgument,
  MeshingSchemaTask,
  MeshingWorkflowContract,
  MeshingWorkflowSchema,
} from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MeshingAutomationCreatePage } from './MeshingAutomationCreatePage'

const argument = (
  name: string,
  displayName: string,
  valueType: string,
  currentValue: unknown,
  overrides: Partial<MeshingSchemaArgument> = {},
): MeshingSchemaArgument => ({
  name,
  display_name: displayName,
  ui_section: '常规',
  edit_path: `workflow.task('task').arguments.${name}`,
  value_type: valueType,
  current_value: currentValue,
  allowed_values: null,
  default_value: currentValue,
  read_only: false,
  editable: true,
  active: true,
  exposure_level: null,
  children: [],
  ...overrides,
})

const task = (
  pythonName: string,
  displayName: string,
  commandName: string,
  taskType: string,
  arguments_: MeshingSchemaArgument[] = [],
  childTemplate: MeshingSchemaTask | null = null,
): MeshingSchemaTask => ({
  python_name: pythonName,
  display_name: displayName,
  command_name: commandName,
  task_type: taskType,
  check_point: 'default-off',
  state: 'Out-of-date',
  task_list: [],
  inactive_task_list: [],
  inactive_tasks: [],
  insertable_tasks: [],
  arguments: arguments_,
  children: [],
  ...(childTemplate
    ? {
        supports_child_template: true,
        child_template: childTemplate,
        child_template_warning: 'fallback',
      }
    : {}),
})

const childTemplate = (
  commandName: string,
  arguments_: MeshingSchemaArgument[],
): MeshingSchemaTask =>
  task('<compound-child-template>', 'Child', commandName, 'Compound Child', arguments_)

const schema: MeshingWorkflowSchema = {
  schema_version: 1,
  fluent_version: '25.2.0',
  workflow_type: 'watertight',
  display_name: 'Watertight Geometry',
  generated_at_utc: 'now',
  tasks: [
    task('import_geometry', 'Import Geometry', 'ImportGeometry', 'Simple', [
      argument('length_unit', 'Units', 'string', 'mm', { allowed_values: ['m', 'cm', 'mm'] }),
      argument('old_zone_list', 'Old Zones', 'list', [], {
        ui_section: '高级选项',
        read_only: true,
        editable: false,
      }),
      argument('directory', 'Directory', 'string', '', {
        ui_section: '开发者/内部',
        exposure_level: 'Developer',
      }),
    ]),
    task(
      'add_local_sizing',
      'Add Local Sizing',
      'AddLocalSizingWTM',
      'Compound',
      [
        argument('add_child', 'Would you like to add local sizing?', 'string', 'no', {
          allowed_values: ['yes', 'no'],
        }),
      ],
      childTemplate('AddLocalSizingWTM', [
        argument('add_child', 'Would you like to add local sizing?', 'string', 'yes'),
        argument('boi_control_name', 'Name', 'string', 'size-big'),
        argument('boi_size', 'Target Mesh Size', 'float', 0.001, {
          display_unit: '$/GlobalSettings/LengthUnit',
        }),
        argument('boi_zoneor_label', 'Select By', 'string', 'label', {
          allowed_values: ['label', 'zone'],
        }),
        argument('boi_face_label_list', 'Labels', 'list', []),
      ]),
    ),
    task(
      'create_surface_mesh',
      'Generate the Surface Mesh',
      'GenerateTheSurfaceMeshWTM',
      'Simple',
      [
        argument('use_size_files', 'Use Custom Size Field/Control Files?', 'string', 'No', {
          allowed_values: ['No', 'Yes'],
        }),
        argument('min_size', 'Minimum Size', 'float', 0.1, {
          display_unit: '$/GlobalSettings/LengthUnit',
        }),
        argument('max_size', 'Maximum Size', 'float', 1, {
          display_unit: '$/GlobalSettings/LengthUnit',
        }),
        argument('growth_rate', 'Growth Rate', 'float', 1.2),
        argument('size_functions', 'Size Functions', 'string', 'Curvature & Proximity', {
          allowed_values: ['Curvature & Proximity', 'Curvature', 'Proximity'],
        }),
      ],
    ),
    task('describe_geometry', 'Describe Geometry', 'GeometrySetup', 'Conditional', [
      argument(
        'setup_type',
        'Geometry Type',
        'string',
        'The geometry consists of only solid regions',
        {
          allowed_values: [
            'The geometry consists of only solid regions',
            'The geometry consists of only fluid regions with no voids',
            'The geometry consists of both fluid and solid regions and/or voids',
          ],
        },
      ),
    ]),
    task('update_regions', 'Update Regions', 'UpdateRegions', 'Simple', [
      argument('mesh_object', 'Mesh Object', 'string', ''),
      argument('region_name_list', 'Region Name List', 'list', []),
      argument('region_type_list', 'Region Type List', 'list', []),
    ]),
    task(
      'add_boundary_layer',
      'Add Boundary Layers',
      'AddBoundaryLayers',
      'Compound',
      [
        argument('add_child', 'Add Boundary Layers?', 'string', 'yes', {
          allowed_values: ['yes', 'no'],
        }),
      ],
      childTemplate('AddBoundaryLayers', [
        argument('add_child', 'Add Boundary Layers?', 'string', 'yes'),
        argument('bl_control_name', 'Name', 'string', 'smooth-transition_1'),
        argument('bl_label_list', 'Labels', 'list', []),
        argument('offset_method_type', 'Offset Method Type', 'string', 'smooth-transition', {
          allowed_values: ['smooth-transition', 'aspect-ratio', 'uniform'],
        }),
        argument('number_of_layers', 'Number of Layers', 'int', 3),
      ]),
    ),
    task('create_volume_mesh', 'Generate the Volume Mesh', 'GenerateTheVolumeMeshWTM', 'Simple', [
      argument('volume_fill', 'Volume Fill', 'string', 'polyhedra', {
        allowed_values: ['polyhedra', 'poly-hexcore', 'hexcore'],
      }),
    ]),
  ],
}

const contract: MeshingWorkflowContract = {
  schema_version: 1,
  fluent_version: '25.2.0',
  workflow_type: 'watertight',
  source_schema: 'docs/meshing/fluent-meshing-25.2-watertight.schema.json',
  step_order: [
    'import_geometry',
    'add_local_sizing',
    'create_surface_mesh',
    'describe_geometry',
    'update_regions',
    'add_boundary_layer',
    'create_volume_mesh',
  ],
  steps: [
    {
      sequence: 1,
      task_path: ['import_geometry'],
      english_name: 'Import Geometry',
      label: '导入几何结构',
      task_type: 'Simple',
      fields: [
        {
          path: ['length_unit'],
          label: 'Units',
          type: 'string',
          control: 'select',
          enum: ['m', 'cm', 'mm'],
          default: 'mm',
          ui_default_override: 'm',
          advanced: false,
          developer: false,
        },
      ],
    },
    {
      sequence: 4,
      task_path: ['describe_geometry'],
      english_name: 'Describe Geometry',
      label: '描述几何结构',
      task_type: 'Conditional',
      fields: [
        {
          path: ['setup_type'],
          label: 'Geometry Type',
          type: 'string',
          control: 'select',
          enum: ['solid', 'fluid', 'fluid_solid_voids'],
          default: 'solid',
          ui_default_override: 'The geometry consists of only fluid regions with no voids',
          advanced: false,
          developer: false,
        },
      ],
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
        workflowSchema: vi.fn().mockResolvedValue(contract),
        validatePreset: vi.fn(),
      },
      meshingAutomations: { create: vi.fn() },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('renders seven horizontal workflow steps and switches step-specific parameters', async () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <MeshingAutomationCreatePage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect((await screen.findAllByRole('button', { name: /导入几何/ })).length).toBeGreaterThan(0)
    for (const name of [
      '导入几何',
      '添加局部尺寸',
      '生成表面网格',
      '描述几何',
      '更新区域',
      '添加边界层',
      '生成体网格',
    ]) {
      expect(screen.getAllByRole('button', { name: new RegExp(name) }).length).toBeGreaterThan(0)
    }
    expect(screen.queryByText('应用共享拓扑')).not.toBeInTheDocument()

    expect(screen.getByText('Units')).toBeInTheDocument()
    expect(screen.getByText('高级与状态选项 (1)')).toBeInTheDocument()
    expect(screen.queryByText('Directory')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('switch'))
    fireEvent.click(await screen.findByText('开发者/内部参数 (1)'))
    expect(await screen.findByText('Directory')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /生成表面网格/ }))
    expect(await screen.findByText('Use Custom Size Field/Control Files?')).toBeInTheDocument()
    expect(screen.getByText('Minimum Size [m]')).toBeInTheDocument()
    expect(screen.getByText('Maximum Size [m]')).toBeInTheDocument()
    expect(screen.getByText('Growth Rate')).toBeInTheDocument()
    expect(screen.getByText('Size Functions')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /添加局部尺寸/ }))
    const localSizingToggle = screen.getByRole('combobox', {
      name: 'Would you like to add local sizing?',
    })
    fireEvent.mouseDown(localSizingToggle)
    fireEvent.click(await screen.findByText('yes', { selector: '.ant-select-item-option-content' }))
    expect(await screen.findByDisplayValue('facesize_1')).toBeInTheDocument()
    expect(await screen.findByText('Target Mesh Size [m]')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /添加复合子任务预设/ }))
    expect(await screen.findByDisplayValue('facesize_2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /添加边界层/ }))
    expect(screen.getByDisplayValue('smooth-transition_1')).toBeInTheDocument()
    expect(await screen.findByText('Number of Layers')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /添加复合子任务预设/ }))
    expect(await screen.findByDisplayValue('smooth-transition_2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /更新区域/ }))
    expect(await screen.findByText('Region Name')).toBeInTheDocument()
    expect(screen.getByText('Region Type')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /添加区域/ }))
    fireEvent.change(screen.getByPlaceholderText('Region Name'), {
      target: { value: 'wenqiuli' },
    })
    expect(screen.getByDisplayValue('wenqiuli')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /描述几何/ }))
    expect(await screen.findByText('几何结构仅由固体区域组成')).toBeInTheDocument()
    expect(screen.getByText('几何结构仅由没有空隙的流体区域组成')).toBeInTheDocument()
    expect(screen.getByText('几何模型同时由流体和固体区域和/或空隙组成')).toBeInTheDocument()
  }, 60_000)
})
