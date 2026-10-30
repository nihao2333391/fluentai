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

export const collectFaceLabels = (items: MeshingPresetItem[]): string[] => {
  const labels = new Set<string>()
  for (const item of items) {
    if (
      ![
        'boi_face_label_list',
        'bl_label_list',
        'zone_selection_list',
        'boundary_label_list',
      ].includes(
        item.argument_path.at(-1) ?? '',
      )
    ) {
      continue
    }
    if (!Array.isArray(item.value)) continue
    for (const value of item.value) {
      if (typeof value === 'string' && value.trim()) labels.add(value.trim())
    }
  }
  return [...labels].sort((left, right) => left.localeCompare(right))
}

export type MeshingIncludedMap = Record<string, boolean>
export type MeshingValueMap = Record<string, MeshingPresetValue>
export type MeshingValueModeMap = Record<string, 'fixed' | 'at_use'>
export type MeshingChildInstanceMap = Record<string, MeshingChildInstance[]>

export interface MeshingArgumentLeaf {
  argument: MeshingSchemaArgument
  argumentPath: string[]
  displayPath: string[]
  parentConditions: string[]
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
  parentConditions: string[] = [],
): MeshingArgumentLeaf[] => {
  const leaves: MeshingArgumentLeaf[] = []
  for (const argument of argumentsToFlatten) {
    if (argument.name === '<arguments>') continue
    const argumentPath = [...parentPath, argument.name]
    const displayPath = [...parentDisplayPath, argument.display_name?.trim() || argument.name]
    if (argument.children.length > 0) {
      leaves.push(...flattenArgumentLeaves(
        argument.children, argumentPath, displayPath,
        argument.display_condition ? [...parentConditions, argument.display_condition] : parentConditions,
      ))
    } else {
      leaves.push({ argument, argumentPath, displayPath, parentConditions })
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

export const buildInitialValues = (
  tasks: MeshingSchemaTask[],
  childInstances: MeshingChildInstanceMap,
): MeshingValueMap => {
  const result: MeshingValueMap = {}
  for (const entry of collectTaskLeaves(tasks)) {
    result[selectionKey(entry.taskPath, null, entry.argumentPath)] = defaultArgumentValue(
      entry.argument,
    )
  }
  for (const task of tasks) {
    if (!task.child_template) continue
    const instances = childInstances[taskPathKey([task.python_name])] ?? []
    for (const instance of instances) {
      for (const leaf of flattenArgumentLeaves(task.child_template.arguments)) {
        if (isManagedChildArgument(task, leaf.argument)) continue
        result[selectionKey([task.python_name], instance.id, leaf.argumentPath)] =
          defaultArgumentValue(leaf.argument)
      }
    }
  }
  return result
}

const indexTasksByPath = (
  tasks: MeshingSchemaTask[],
  parentPath: string[] = [],
  result: Map<string, MeshingSchemaTask> = new Map(),
): Map<string, MeshingSchemaTask> => {
  for (const task of tasks) {
    const taskPath = [...parentPath, task.python_name]
    result.set(taskPathKey(taskPath), task)
    indexTasksByPath(task.children, taskPath, result)
  }
  return result
}

let childInstanceCounter = 0

export const nextChildInstanceId = (task: MeshingSchemaTask): string => {
  childInstanceCounter += 1
  return `${task.python_name}-${childInstanceCounter}`
}

export const restoreEditorState = (
  tasks: MeshingSchemaTask[],
  presetItems: MeshingPresetItem[],
): {
  childInstances: MeshingChildInstanceMap
  included: MeshingIncludedMap
  values: MeshingValueMap
} => {
  const tasksByPath = indexTasksByPath(tasks)
  const childInstances: MeshingChildInstanceMap = {}

  for (const item of presetItems) {
    if (!item.compound_child_name) continue
    const task = tasksByPath.get(taskPathKey(item.task_path))
    if (!task) continue
    const key = taskPathKey(item.task_path)
    const instances = childInstances[key] ?? []
    if (!instances.some((instance) => instance.name === item.compound_child_name)) {
      instances.push({
        id: nextChildInstanceId(task),
        name: item.compound_child_name,
        optional: true,
      })
      childInstances[key] = instances
    }
  }

  const values = buildInitialValues(tasks, childInstances)
  const included: MeshingIncludedMap = {}
  for (const item of presetItems) {
    const task = tasksByPath.get(taskPathKey(item.task_path))
    if (!task) continue
    let childInstanceId: string | null = null
    if (item.compound_child_name) {
      const instance = (childInstances[taskPathKey(item.task_path)] ?? []).find(
        (candidate) => candidate.name === item.compound_child_name,
      )
      if (!instance) continue
      if (childNameArgument(task)?.name === item.argument_path[0]) continue
      childInstanceId = instance.id
    }
    const key = selectionKey(item.task_path, childInstanceId, item.argument_path)
    if (item.value_mode === 'at_use') continue
    if (childInstanceId) {
      const instances = childInstances[taskPathKey(item.task_path)] ?? []
      const instance = instances.find((candidate) => candidate.id === childInstanceId)
      if (instance) instance.optional = false
    }
    included[key] = true
    values[key] = item.value
  }

  return { childInstances, included, values }
}

const splitCondition = (source: string, operator: ' or ' | ' and '): string[] => {
  const parts: string[] = []
  let depth = 0
  let quote: string | null = null
  let start = 0
  for (let index = 0; index <= source.length - operator.length; index += 1) {
    const char = source[index]
    if (quote) {
      if (char === quote && source[index - 1] !== '\\') quote = null
      continue
    }
    if (char === '"' || char === "'") quote = char
    else if (char === '(') depth += 1
    else if (char === ')') depth -= 1
    else if (
      depth === 0 &&
      source.slice(index, index + operator.length).toLowerCase() === operator
    ) {
      parts.push(source.slice(start, index).trim())
      start = index + operator.length
      index = start - 1
    }
  }
  if (parts.length === 0) return [source.trim()]
  parts.push(source.slice(start).trim())
  return parts
}

const normalizeArgumentIdentifier = (value: string): string =>
  value.replace(/[^a-z0-9]/gi, '').toLowerCase()

const conditionValue = (
  source: string,
  task: MeshingSchemaTask,
  taskPath: string[],
  childInstanceId: string | null,
  values: MeshingValueMap,
): unknown => {
  const token = source.trim()
  if (
    (token.startsWith('"') && token.endsWith('"')) ||
    (token.startsWith("'") && token.endsWith("'"))
  ) {
    return token.slice(1, -1)
  }
  if (token.toLowerCase() === 'true' || token.toLowerCase() === 'false')
    return token.toLowerCase() === 'true'
  if (/^-?\d+(?:\.\d+)?$/.test(token)) return Number(token)
  if (/^[A-Za-z][\w-]*$/.test(token)) return token
  const reference = token.match(/^\$\.\.\/(?:\.\.\/)*((?:[A-Za-z_]\w*\/)*[A-Za-z_]\w*)$/)
  if (!reference) return undefined
  const referenceName = reference[1].split('/').at(-1) ?? ''
  const normalizedReferenceName = normalizeArgumentIdentifier(referenceName)
  const sourceArguments = childInstanceId ? (task.child_template?.arguments ?? []) : task.arguments
  const leaf = flattenArgumentLeaves(sourceArguments).find(
    (candidate) => [candidate.argument.name, candidate.argument.source_name].some(
      (name) => name && normalizeArgumentIdentifier(name) === normalizedReferenceName,
    ),
  )
  if (!leaf) return undefined
  const key = selectionKey(taskPath, childInstanceId, leaf.argumentPath)
  return values[key] ?? defaultArgumentValue(leaf.argument)
}

const hasWrappingParentheses = (source: string): boolean => {
  if (!source.startsWith('(') || !source.endsWith(')')) return false
  let depth = 0
  let quote: string | null = null
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    if (quote) {
      if (char === quote && source[index - 1] !== '\\') quote = null
      continue
    }
    if (char === '"' || char === "'") quote = char
    else if (char === '(') depth += 1
    else if (char === ')') {
      depth -= 1
      if (depth === 0 && index !== source.length - 1) return false
    }
  }
  return depth === 0
}

const evaluateCondition = (
  expression: string,
  task: MeshingSchemaTask,
  taskPath: string[],
  childInstanceId: string | null,
  values: MeshingValueMap,
): boolean | undefined => {
  let source = expression.trim()
  while (hasWrappingParentheses(source)) source = source.slice(1, -1).trim()
  const alternatives = splitCondition(source, ' or ')
  if (alternatives.length > 1) {
    const results = alternatives.map((part) =>
      evaluateCondition(part, task, taskPath, childInstanceId, values),
    )
    if (results.includes(true)) return true
    return results.includes(undefined) ? undefined : false
  }
  const conjunctions = splitCondition(source, ' and ')
  if (conjunctions.length > 1) {
    const results = conjunctions.map((part) =>
      evaluateCondition(part, task, taskPath, childInstanceId, values),
    )
    if (results.includes(false)) return false
    return results.includes(undefined) ? undefined : true
  }
  if (source.toLowerCase().startsWith('not ')) {
    const value = evaluateCondition(source.slice(4), task, taskPath, childInstanceId, values)
    return value === undefined ? undefined : !value
  }
  const comparison = source.match(/^(.+?)\s*(==|!=)\s*(.+)$/)
  if (comparison) {
    const left = conditionValue(comparison[1], task, taskPath, childInstanceId, values)
    const right = conditionValue(comparison[3], task, taskPath, childInstanceId, values)
    if (left === undefined || right === undefined) return undefined
    const equal = String(left) === String(right)
    return comparison[2] === '==' ? equal : !equal
  }
  const value = conditionValue(source, task, taskPath, childInstanceId, values)
  return value === undefined ? undefined : Boolean(value)
}

export const isArgumentConditionVisible = (
  argument: MeshingSchemaArgument,
  task: MeshingSchemaTask,
  taskPath: string[],
  childInstanceId: string | null,
  values: MeshingValueMap,
  argumentPath: string[] = [argument.name],
  parentConditions: string[] = [],
): boolean => {
  const valueOf = (name: string, childId: string | null = childInstanceId): string => {
    const args = childId ? (task.child_template?.arguments ?? []) : task.arguments
    const leaf = flattenArgumentLeaves(args).find((candidate) => candidate.argument.name === name)
    return String(leaf ? values[selectionKey(taskPath, childId, leaf.argumentPath)] ??
      defaultArgumentValue(leaf.argument) : '')
  }
  const root = argumentPath[0]
  if (task.python_name === 'import_geometry') {
    const fileFormat = String(
      values[selectionKey(['import_geometry'], null, ['file_format'])] ??
        valueOf('file_format') ??
        'CAD',
    ) || 'CAD'
    if (argument.name === 'length_unit') return fileFormat === 'CAD'
    if (argument.name === 'mesh_unit') return fileFormat === 'Mesh'
  }
  if (task.python_name === 'create_surface_mesh') {
    const conditionallyManagedArguments = [
      'cfd_surface_mesh_controls',
      'surface_mesh_preferences',
      'separation_required',
      'separation_angle',
      'remesh_selection_type',
      'remesh_zone_list',
      'remesh_label_list',
    ]
    if (!conditionallyManagedArguments.includes(root)) {
      return argument.name !== 'surface_mesh_method'
    }
    const importedMesh = String(values[selectionKey(['import_geometry'], null, ['file_format'])] ?? 'CAD') === 'Mesh'
    const remesh = valueOf('remesh_imported_mesh')
    const selection = valueOf('remesh_selection_type')
    const sizeFunction = valueOf('size_functions')
    if (argument.name === 'surface_mesh_method') return false
    if (argument.name === 'remesh_imported_mesh') return importedMesh
    if (argument.name === 'remesh_selection_type') return importedMesh && remesh.includes('Selected')
    if (argument.name === 'remesh_zone_list') return importedMesh && remesh.includes('Selected') && selection === 'zone'
    if (argument.name === 'remesh_label_list') return importedMesh && remesh.includes('Selected') && selection === 'label'
    if (argument.name === 'curvature_normal_angle') return sizeFunction.includes('Curvature')
    if (['cells_per_gap', 'scope_proximity_to', 'object_based_controls'].includes(argument.name))
      return sizeFunction.includes('Proximity')
    if (argument.name === 'separation_angle') return valueOf('separation_required') === 'Yes'
  }
  if (task.python_name === 'add_boundary_layer') {
    const offset = valueOf('offset_method_type')
    const growOn = valueOf('grow_on')
    const regions = valueOf('regions_type')
    if (argument.name === 'first_aspect_ratio') return offset === 'aspect-ratio'
    if (argument.name === 'transition_ratio') return ['smooth-transition', 'last-ratio'].includes(offset)
    if (argument.name === 'rate') return offset !== 'last-ratio'
    if (argument.name === 'first_height') return ['last-ratio', 'uniform'].includes(offset)
    if (argument.name === 'bl_label_list') return growOn === 'selected-labels'
    if (argument.name === 'zone_selection_list') return growOn === 'selected-zones'
    if (argument.name === 'region_scope') return ['named-regions', 'named-fluid-regions'].includes(regions)
  }
  if (task.python_name === 'create_volume_mesh') {
    if (!['solver', 'volume_fill', 'mesh_fluid_regions', 'mesh_solid_regions', 'sizing_method',
      'volume_fill_controls', 're_merge_zones', 'parallel_meshing', 'volume_mesh_preferences',
      'prism_preferences', 'global_thin_volume_preferences'].includes(root)) return false
    if (root === 'region_based_preferences') return false
    const fill = valueOf('volume_fill')
    const hex = ['hexcore', 'poly-hexcore'].includes(fill)
    if (['buffer_layers', 'peel_layers', 'hex_min_cell_length', 'hex_max_cell_length'].includes(argument.name)) return hex
    if (['growth_rate', 'tet_poly_max_cell_length'].includes(argument.name)) return !hex
    if (root === 'prism_preferences' &&
        values[selectionKey(['add_boundary_layer'], null, ['add_child'])] !== 'yes') return false
    if (root === 'global_thin_volume_preferences') return false
  }
  if (task.python_name === 'add_local_sizing') {
    const args = childInstanceId ? (task.child_template?.arguments ?? []) : task.arguments
    const localValue = (name: string): unknown => {
      const leaf = flattenArgumentLeaves(args).find(
        (candidate) => candidate.argument.name.toLowerCase() === name.toLowerCase(),
      )
      if (!leaf) return undefined
      return (
        values[selectionKey(taskPath, childInstanceId, leaf.argumentPath)] ??
        defaultArgumentValue(leaf.argument)
      )
    }
    const controlType = String(localValue('boi_execution') ?? '')
    const selectBy = String(localValue('boi_zoneor_label') ?? '')
    const scopeTo = String(localValue('boi_scope_to') ?? '')
    const assignSizeUsing = String(localValue('assign_size_using') ?? '')
    const growthMethod = String(localValue('growth_method') ?? '')
    const growthPattern = String(localValue('growth_pattern') ?? '')
    const edgeSizeSupported =
      flattenArgumentLeaves(args)
        .find((candidate) => candidate.argument.name === 'boi_execution')
        ?.argument.allowed_values?.some((item) => String(item) === 'Edge Size') ?? false

    if (
      [
        'assign_size_using',
        'numberof_layers',
        'smallest_height',
        'growth_pattern',
        'growth_method',
        'bias_factor',
      ].includes(argument.name)
    ) {
      if (!edgeSizeSupported || controlType !== 'Edge Size') return false
      if (argument.name === 'numberof_layers') return assignSizeUsing === 'Interval'
      if (argument.name === 'smallest_height') return assignSizeUsing === 'Smallest Height'
      if (argument.name === 'growth_method')
        return growthPattern !== '_____ _____ _____ _____ _____'
      if (argument.name === 'bias_factor') {
        return growthMethod === 'Bias Factor' && growthPattern !== '_____ _____ _____ _____ _____'
      }
      return true
    }
    if (argument.name === 'boi_growth_rate' && ['Curvature', 'Proximity'].includes(controlType)) {
      return false
    }
    if (argument.name === 'boi_curvature_normal_angle') return controlType === 'Curvature'
    if (argument.name === 'boi_cells_per_gap') return controlType === 'Proximity'
    if (['boi_min_size', 'boi_max_size'].includes(argument.name)) {
      return ['Curvature', 'Proximity'].includes(controlType)
    }
    if (argument.name === 'boi_scope_to') {
      return ['Curvature', 'Proximity'].includes(controlType)
    }
    if (argument.name === 'boi_face_label_list') {
      return selectBy === 'label' && controlType !== 'Edge Size' && scopeTo !== 'edge labels'
    }
    if (argument.name === 'boi_face_zone_list') {
      return selectBy === 'zone' && controlType !== 'Edge Size' && scopeTo !== 'edge labels'
    }
    if (argument.name === 'edge_label_list') {
      return selectBy === 'label' && (controlType === 'Edge Size' || scopeTo === 'edge labels')
    }
    if (argument.name === 'edge_zone_list') {
      return selectBy === 'zone' && (controlType === 'Edge Size' || scopeTo === 'edges')
    }
    if (argument.name === 'topology_list') {
      return selectBy === 'topology' && controlType !== 'Edge Size' && scopeTo !== 'edge labels'
    }
    if (argument.name === 'ignore_orientation') {
      return controlType === 'Proximity' && !['edges', 'edge labels'].includes(scopeTo)
    }
  }
  const conditions = [...parentConditions, ...(argument.display_condition ? [argument.display_condition] : [])]
  const results = conditions.map((condition) =>
    evaluateCondition(condition, task, taskPath, childInstanceId, values),
  )
  if (results.includes(false)) return false
  // Fluent marks fields disabled by engine-only S_* conditions as inactive.
  // Use that snapshot metadata when the renderer cannot evaluate a condition.
  if (results.includes(undefined)) return argument.active !== false
  return true
}

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
  valueModes: MeshingValueModeMap = {},
): MeshingBuildResult => {
  const items: MeshingPresetItem[] = []
  const issues: MeshingBuildIssue[] = []

  const appendLeaf = (
    task: MeshingSchemaTask,
    taskPath: string[],
    childInstanceId: string | null,
    childName: string | null,
    leaf: MeshingArgumentLeaf,
  ) => {
    const key = selectionKey(taskPath, childInstanceId, leaf.argumentPath)
    if (!included[key]) return
    if (!isArgumentConditionVisible(leaf.argument, task, taskPath, childInstanceId, values, leaf.argumentPath, leaf.parentConditions)) return
    if (
      taskPath[0] === 'import_geometry' &&
      ['file_name', 'file_names', 'mesh_file_name'].includes(leaf.argumentPath.at(-1) ?? '')
    )
      return
    const valueMode = valueModes[key] ?? 'fixed'
    items.push({
      task_path: taskPath,
      argument_path: leaf.argumentPath,
      value: valueMode === 'at_use' ? null : (values[key] ?? defaultArgumentValue(leaf.argument)),
      value_mode: valueMode,
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
      const defaultToggle = toggleArgument
        ? String(defaultArgumentValue(toggleArgument)).toLowerCase()
        : 'no'
      if (toggleArgument && toggleValue.toLowerCase() !== defaultToggle) {
        items.push({
          task_path: taskPath,
          argument_path: ['add_child'],
          value: toggleValue,
          value_mode: 'fixed',
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
        const selectedLeaves = leaves.filter(
          (leaf) =>
            Boolean(included[selectionKey(taskPath, instance.id, leaf.argumentPath)]) &&
            isArgumentConditionVisible(leaf.argument, task, taskPath, instance.id, values, leaf.argumentPath, leaf.parentConditions),
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
            value_mode: 'fixed',
            required: true,
            compound_child_name: childName,
          })
        }
        for (const leaf of selectedLeaves) {
          appendLeaf(task, taskPath, instance.id, childName, leaf)
        }
      }
    } else {
      for (const leaf of flattenArgumentLeaves(task.arguments)) {
        appendLeaf(task, taskPath, null, null, leaf)
      }
    }
    for (const child of task.children) visitTask(child, taskPath)
  }

  for (const task of schemaTasks) visitTask(task, [])
  return { items, issues }
}
