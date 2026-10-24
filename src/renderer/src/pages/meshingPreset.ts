import type {
  MeshingPresetItem,
  MeshingPresetValue,
  MeshingSchemaArgument,
  MeshingSchemaTask,
} from '../../../shared/contracts'

export interface MeshingChildInstance {
  id: string
  name: string
  optional?: boolean
}

export type MeshingIncludedMap = Record<string, boolean>
export type MeshingValueMap = Record<string, MeshingPresetValue>
export type MeshingChildInstanceMap = Record<string, MeshingChildInstance[]>

export interface MeshingArgumentLeaf {
  argument: MeshingSchemaArgument
  argumentPath: string[]
  displayPath: string[]
}

export interface MeshingTaskLeaf extends MeshingArgumentLeaf {
  task: MeshingSchemaTask
  taskPath: string[]
}

export interface MeshingBuildIssue {
  code: 'childNameRequired' | 'duplicateChildName' | 'childHasNoSelection'
  taskName: string
  childName?: string
}

export interface MeshingBuildResult {
  items: MeshingPresetItem[]
  issues: MeshingBuildIssue[]
}

const CHILD_NAME_ARGUMENTS = new Set([
  'boi_control_name',
  'bl_control_name',
  'local_settings_name',
  'leakage_name',
  'extract_edges_name',
  'zero_thickness_name',
  'material_points_name',
])

export const taskPathKey = (taskPath: string[]): string => JSON.stringify(taskPath)

export const selectionKey = (
  taskPath: string[],
  childInstanceId: string | null,
  argumentPath: string[],
): string => JSON.stringify([taskPath, childInstanceId, argumentPath])

export const isAdvancedArgument = (argument: MeshingSchemaArgument): boolean => {
  if (argument.ui_section === '高级选项') return true
  if (argument.ui_section === '开发者/内部' || argument.ui_section === '常规') return false
  const exposure = String(argument.exposure_level ?? '').toLowerCase()
  if (exposure === 'advanced' || exposure === 'expert' || exposure === '2') {
    return true
  }
  if (argument.editable === false || argument.read_only === true || argument.active === false) {
    return true
  }
  return /^(old_|current_|allowed_|complete_|mesh_object|topology|zone_location|list_all_|draw_|preview_|show_|save_|write_)/.test(
    argument.name,
  )
}

export const isDeveloperArgument = (argument: MeshingSchemaArgument): boolean => {
  if (argument.ui_section === '开发者/内部') return true
  return String(argument.exposure_level ?? '').toLowerCase() === 'developer'
}

export const defaultArgumentValue = (argument: MeshingSchemaArgument): MeshingPresetValue => {
  if (argument.default_value !== null && argument.default_value !== undefined) {
    return argument.default_value as MeshingPresetValue
  }
  if (argument.current_value !== null && argument.current_value !== undefined) {
    return argument.current_value as MeshingPresetValue
  }
  if (argument.allowed_values?.length) return argument.allowed_values[0]
  if (argument.value_type === 'bool') return false
  if (argument.value_type === 'int') return 0
  if (argument.value_type === 'float') return 0
  if (argument.value_type === 'list' || argument.value_type === 'RepeatedScalarContainer') return []
  if (argument.value_type === 'object') return {}
  return ''
}

export const flattenArgumentLeaves = (
  argumentsToFlatten: MeshingSchemaArgument[],
  parentPath: string[] = [],
  parentDisplayPath: string[] = [],
): MeshingArgumentLeaf[] => {
  const leaves: MeshingArgumentLeaf[] = []
  for (const argument of argumentsToFlatten) {
    if (argument.name === '<arguments>') continue
    const argumentPath = [...parentPath, argument.name]
    const displayPath = [...parentDisplayPath, argument.display_name?.trim() || argument.name]
    if (argument.children.length > 0) {
      leaves.push(...flattenArgumentLeaves(argument.children, argumentPath, displayPath))
    } else {
      leaves.push({ argument, argumentPath, displayPath })
    }
  }
  return leaves
}

export const collectTaskLeaves = (
  tasks: MeshingSchemaTask[],
  parentPath: string[] = [],
): MeshingTaskLeaf[] => {
  const leaves: MeshingTaskLeaf[] = []
  for (const task of tasks) {
    const taskPath = [...parentPath, task.python_name]
    if (!(task.supports_child_template && task.child_template)) {
      for (const leaf of flattenArgumentLeaves(task.arguments)) {
        leaves.push({ task, taskPath, ...leaf })
      }
    }
    leaves.push(...collectTaskLeaves(task.children, taskPath))
  }
  return leaves
}

export const childNameArgument = (task: MeshingSchemaTask): MeshingSchemaArgument | undefined =>
  task.child_template?.arguments.find((argument) => CHILD_NAME_ARGUMENTS.has(argument.name))

export const isManagedChildArgument = (
  task: MeshingSchemaTask,
  argument: MeshingSchemaArgument,
): boolean => argument.name === 'add_child' || childNameArgument(task)?.name === argument.name

export const defaultChildName = (task: MeshingSchemaTask, index: number): string => {
  const argumentName = childNameArgument(task)?.name
  if (argumentName === 'bl_control_name' && argumentName) return `smooth-transition_${index}`
  if (argumentName === 'boi_control_name') return `facesize_${index}`
  if (argumentName === 'material_points_name') return `region-${index}`
  if (argumentName === 'leakage_name') return `leakage-${index}`
  if (argumentName === 'extract_edges_name') return `edge-group-${index}`
  if (argumentName === 'zero_thickness_name') return `face-group-${index}`
  return `local-sizing_${index}`
}

export const buildMeshingPresetItems = (
  schemaTasks: MeshingSchemaTask[],
  included: MeshingIncludedMap,
  values: MeshingValueMap,
  childInstances: MeshingChildInstanceMap,
): MeshingBuildResult => {
  const items: MeshingPresetItem[] = []
  const issues: MeshingBuildIssue[] = []

  const appendLeaf = (
    taskPath: string[],
    childInstanceId: string | null,
    childName: string | null,
    leaf: MeshingArgumentLeaf,
  ) => {
    const key = selectionKey(taskPath, childInstanceId, leaf.argumentPath)
    if (!included[key]) return
    items.push({
      task_path: taskPath,
      argument_path: leaf.argumentPath,
      value: values[key] ?? defaultArgumentValue(leaf.argument),
      required: true,
      compound_child_name: childName,
    })
  }

  const visitTask = (task: MeshingSchemaTask, parentPath: string[]) => {
    const taskPath = [...parentPath, task.python_name]
    if (task.supports_child_template && task.child_template) {
      const toggleArgument = task.arguments.find((argument) => argument.name === 'add_child')
      const toggleKey = selectionKey(taskPath, null, ['add_child'])
      const toggleValue = String(
        values[toggleKey] ?? (toggleArgument ? defaultArgumentValue(toggleArgument) : 'no'),
      )
      if (toggleArgument) {
        items.push({
          task_path: taskPath,
          argument_path: ['add_child'],
          value: toggleValue,
          required: true,
          compound_child_name: null,
        })
      }
      if (toggleArgument && !toggleValue.toLowerCase().startsWith('yes')) {
        for (const child of task.children) visitTask(child, taskPath)
        return
      }
      const instances = childInstances[taskPathKey(taskPath)] ?? []
      const seenNames = new Set<string>()
      for (const instance of instances) {
        const childName = instance.name.trim()
        if (!childName) {
          issues.push({ code: 'childNameRequired', taskName: task.display_name })
          continue
        }
        const normalizedName = childName.toLocaleLowerCase()
        if (seenNames.has(normalizedName)) {
          issues.push({ code: 'duplicateChildName', taskName: task.display_name, childName })
          continue
        }
        seenNames.add(normalizedName)

        const leaves = flattenArgumentLeaves(task.child_template.arguments).filter(
          (leaf) => !isManagedChildArgument(task, leaf.argument),
        )
        const selectedLeaves = leaves.filter((leaf) =>
          Boolean(included[selectionKey(taskPath, instance.id, leaf.argumentPath)]),
        )
        if (selectedLeaves.length === 0) {
          if (!instance.optional) {
            issues.push({ code: 'childHasNoSelection', taskName: task.display_name, childName })
          }
          continue
        }
        const nameArgument = childNameArgument(task)
        if (nameArgument) {
          items.push({
            task_path: taskPath,
            argument_path: [nameArgument.name],
            value: childName,
            required: true,
            compound_child_name: childName,
          })
        }
        for (const leaf of selectedLeaves) {
          appendLeaf(taskPath, instance.id, childName, leaf)
        }
      }
    } else {
      for (const leaf of flattenArgumentLeaves(task.arguments)) {
        appendLeaf(taskPath, null, null, leaf)
      }
    }
    for (const child of task.children) visitTask(child, taskPath)
  }

  for (const task of schemaTasks) visitTask(task, [])
  return { items, issues }
}
