import { describe, expect, it } from 'vitest'

import type { MeshingSchemaTask } from '../../../shared/contracts'
import {
  buildMeshingPresetItems,
  flattenArgumentLeaves,
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
  it('flattens nested object arguments with their full paths', () => {
    expect(flattenArgumentLeaves(childTemplate.arguments).map((leaf) => leaf.argumentPath)).toEqual(
      [
        ['add_child'],
        ['boi_control_name'],
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
})
