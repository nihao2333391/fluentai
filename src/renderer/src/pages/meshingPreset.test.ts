import { describe, expect, it } from 'vitest'

import type { MeshingSchemaTask } from '../../../shared/contracts'
import {
  buildMeshingPresetItems,
  flattenArgumentLeaves,
  isArgumentConditionVisible,
  restoreEditorState,
  selectionKey,
  taskPathKey,
  type MeshingChildInstanceMap,
} from './meshingPreset'

const argument = (
  name: string,
  valueType: string,
  currentValue: unknown,
): MeshingSchemaTask['arguments'][number] => ({
  name,
  edit_path: `workflow.task('task').command_arguments.${name}`,
  value_type: valueType,
  current_value: currentValue,
  allowed_values: null,
  default_value: currentValue,
  read_only: false,
  editable: true,
  active: true,
  exposure_level: null,
  children: [],
})

const childTemplate: MeshingSchemaTask = {
  python_name: '<compound-child-template>',
  display_name: 'Child',
  command_name: 'AddLocalSizingWTM',
  task_type: 'Compound Child',
  check_point: '',
  state: '',
  task_list: null,
  inactive_task_list: null,
  inactive_tasks: [],
  insertable_tasks: [],
  arguments: [
    argument('add_child', 'string', 'yes'),
    argument('boi_control_name', 'string', 'facesize_1'),
    argument('boi_execution', 'string', 'Face Size'),
    argument('boi_zoneor_label', 'string', 'label'),
    argument('boi_face_label_list', 'list', []),
    {
      ...argument('volume_preferences', 'object', {}),
      children: [argument('show_volume_mesh_preferences', 'bool', false)],
    },
  ],
  children: [],
}

const task: MeshingSchemaTask = {
  python_name: 'add_local_sizing',
  display_name: 'Add Local Sizing',
  command_name: 'AddLocalSizingWTM',
  task_type: 'Compound',
  check_point: 'default-off',
  state: 'Out-of-date',
  task_list: null,
  inactive_task_list: null,
  inactive_tasks: [],
  insertable_tasks: [],
  supports_child_template: true,
  child_template: childTemplate,
  arguments: [],
  children: [],
}

describe('meshingPreset', () => {
  it('shows only local sizing fields that match the selected Fluent size control type', () => {
    const sizingArgs = [
      {
        ...argument('boi_execution', 'string', 'Face Size'),
        allowed_values: ['Face Size', 'Curvature', 'Proximity'],
      },
      { ...argument('boi_zoneor_label', 'string', 'label'), allowed_values: ['label', 'zone'] },
      {
        ...argument('boi_scope_to', 'string', 'faces'),
        display_condition: '$../BOIExecution == "Curvature" or $../BOIExecution == "Proximity"',
      },
      {
        ...argument('boi_growth_rate', 'float', 1.2),
        display_condition: 'S_ActiveBOIGrowthRate(...)',
      },
      {
        ...argument('bias_factor', 'float', 1.2),
        display_condition:
          '$/GlobalSettings/EnablePrimeMeshing and $../BOIExecution == "Edge Size"',
      },
      {
        ...argument('boi_min_size', 'float', 0.001),
        display_condition: '$../BOIExecution == "Curvature" or $../BOIExecution == "Proximity"',
      },
      {
        ...argument('boi_curvature_normal_angle', 'float', 18),
        display_condition: '$../BOIExecution == "Curvature"',
      },
      {
        ...argument('boi_cells_per_gap', 'int', 3),
        display_condition: '$../BOIExecution == "Proximity"',
      },
      {
        ...argument('boi_face_label_list', 'list', []),
        display_condition: 'S_SCFaceLabelActive(...)',
      },
    ]
    const sizingTask: MeshingSchemaTask = {
      ...task,
      child_template: { ...childTemplate, arguments: sizingArgs },
    }
    const childId = 'size-1'
    const visible = (name: string, mode: string): boolean => {
      const field = sizingArgs.find((item) => item.name === name)!
      const values = {
        [selectionKey(['add_local_sizing'], childId, ['boi_execution'])]: mode,
        [selectionKey(['add_local_sizing'], childId, ['boi_zoneor_label'])]: 'label',
        [selectionKey(['add_local_sizing'], childId, ['boi_scope_to'])]: 'faces',
      }
      return isArgumentConditionVisible(field, sizingTask, ['add_local_sizing'], childId, values)
    }

    expect(visible('boi_face_label_list', 'Face Size')).toBe(true)
    expect(visible('bias_factor', 'Face Size')).toBe(false)
    expect(visible('boi_min_size', 'Face Size')).toBe(false)
    expect(visible('boi_min_size', 'Curvature')).toBe(true)
    expect(visible('boi_curvature_normal_angle', 'Curvature')).toBe(true)
    expect(visible('boi_cells_per_gap', 'Curvature')).toBe(false)
    expect(visible('boi_cells_per_gap', 'Proximity')).toBe(true)
    expect(visible('boi_growth_rate', 'Proximity')).toBe(false)
  })

  it('saves and restores boundary label mappings when Fluent condition names use PascalCase', () => {
    const boundaryTask: MeshingSchemaTask = {
      ...task,
      python_name: 'update_boundaries',
      display_name: 'Update Boundaries',
      supports_child_template: false,
      child_template: null,
      arguments: [
        {
          ...argument('selection_type', 'string', 'zone'),
          display_name: 'Selection Type',
          allowed_values: ['zone', 'label'],
        },
        {
          ...argument('boundary_label_list', 'list', []),
          display_name: 'BoundaryLabelList',
          active: false,
          display_condition: '$../SelectionType == "label"',
        },
        {
          ...argument('boundary_label_type_list', 'list', []),
          display_name: 'BoundaryLabelTypeList',
          active: false,
          display_condition: '$../SelectionType == "label"',
        },
      ],
    }
    const labels = ['inlet-cold', 'inlet-hot', 'outlet', 'wall-big', 'wall-small']
    const boundaryTypes = [
      'velocity-inlet',
      'velocity-inlet',
      'pressure-outlet',
      'wall',
      'wall',
    ]
    const values = {
      [selectionKey(['update_boundaries'], null, ['selection_type'])]: 'label',
      [selectionKey(['update_boundaries'], null, ['boundary_label_list'])]: labels,
      [selectionKey(['update_boundaries'], null, ['boundary_label_type_list'])]: boundaryTypes,
    }
    const included = Object.fromEntries(Object.keys(values).map((key) => [key, true]))

    const result = buildMeshingPresetItems([boundaryTask], included, values, {})

    expect(result.issues).toEqual([])
    expect(result.items).toEqual([
      expect.objectContaining({
        task_path: ['update_boundaries'],
        argument_path: ['selection_type'],
        value: 'label',
      }),
      expect.objectContaining({
        task_path: ['update_boundaries'],
        argument_path: ['boundary_label_list'],
        value: labels,
      }),
      expect.objectContaining({
        task_path: ['update_boundaries'],
        argument_path: ['boundary_label_type_list'],
        value: boundaryTypes,
      }),
    ])

    const restored = restoreEditorState([boundaryTask], result.items)
    expect(restored.included[selectionKey(['update_boundaries'], null, ['selection_type'])]).toBe(
      true,
    )
    expect(restored.values[selectionKey(['update_boundaries'], null, ['selection_type'])]).toBe(
      'label',
    )
    expect(
      restored.values[selectionKey(['update_boundaries'], null, ['boundary_label_list'])],
    ).toEqual(labels)
    expect(
      restored.values[selectionKey(['update_boundaries'], null, ['boundary_label_type_list'])],
    ).toEqual(boundaryTypes)
  })

  it('flattens nested object arguments with their full paths', () => {
    expect(flattenArgumentLeaves(childTemplate.arguments).map((leaf) => leaf.argumentPath)).toEqual(
      [
        ['add_child'],
        ['boi_control_name'],
        ['boi_execution'],
        ['boi_zoneor_label'],
        ['boi_face_label_list'],
        ['volume_preferences', 'show_volume_mesh_preferences'],
      ],
    )
  })

  it('builds named compound child items and omits managed add_child', () => {
    const instance = { id: 'child-1', name: 'wall-big' }
    const childInstances: MeshingChildInstanceMap = {
      [taskPathKey(['add_local_sizing'])]: [instance],
    }
    const included = {
      [selectionKey(['add_local_sizing'], instance.id, ['boi_face_label_list'])]: true,
      [selectionKey(['add_local_sizing'], instance.id, [
        'volume_preferences',
        'show_volume_mesh_preferences',
      ])]: true,
    }
    const values = {
      [selectionKey(['add_local_sizing'], instance.id, ['boi_face_label_list'])]: ['wall-big'],
      [selectionKey(['add_local_sizing'], instance.id, [
        'volume_preferences',
        'show_volume_mesh_preferences',
      ])]: true,
    }

    const result = buildMeshingPresetItems([task], included, values, childInstances)

    expect(result.issues).toEqual([])
    expect(result.items).toHaveLength(3)
    expect(result.items.map((item) => item.argument_path)).toEqual([
      ['boi_control_name'],
      ['boi_face_label_list'],
      ['volume_preferences', 'show_volume_mesh_preferences'],
    ])
    expect(result.items.every((item) => item.compound_child_name === 'wall-big')).toBe(true)
  })

  it('reports duplicate child names and empty child selections', () => {
    const childInstances: MeshingChildInstanceMap = {
      [taskPathKey(['add_local_sizing'])]: [
        { id: 'child-1', name: 'wall-big' },
        { id: 'child-2', name: 'WALL-BIG' },
      ],
    }
    const result = buildMeshingPresetItems([task], {}, {}, childInstances)
    expect(result.issues.map((issue) => issue.code)).toEqual([
      'childHasNoSelection',
      'duplicateChildName',
    ])
  })

  it('skips fixed optional children when the user leaves them empty', () => {
    const childInstances: MeshingChildInstanceMap = {
      [taskPathKey(['add_local_sizing'])]: [
        { id: 'size-big', name: 'size-big', optional: true },
        { id: 'size-small', name: 'size-small', optional: true },
      ],
    }
    const result = buildMeshingPresetItems([task], {}, {}, childInstances)

    expect(result.issues).toEqual([])
    expect(result.items).toEqual([])
  })
})
