import {
  CheckOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  Radio,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMatch, useNavigate } from 'react-router-dom'

import type {
  MeshingAutomation,
  MeshingPresetDocument,
  MeshingPresetItem,
  MeshingPresetValue,
  MeshingSchemaArgument,
  MeshingSchemaTask,
  MeshingWorkflowContract,
  MeshingWorkflowSchema,
  MeshingWorkflowType,
  Model,
} from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { localizedAnsysTerm, localizedAnsysValue } from '../i18n/ansysLabels'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'
import {
  buildMeshingPresetItems,
  childNameArgument,
  collectTaskLeaves,
  defaultArgumentValue,
  defaultChildName,
  flattenArgumentLeaves,
  isAdvancedArgument,
  isDeveloperArgument,
  isManagedChildArgument,
  selectionKey,
  taskPathKey,
  type MeshingArgumentLeaf,
  type MeshingChildInstance,
  type MeshingChildInstanceMap,
  type MeshingIncludedMap,
  type MeshingValueMap,
} from './meshingPreset'
import { localizedMeshingTaskName, localizedMeshingTaskType } from './meshingLabels'

interface MeshingFormValues {
  name: string
  description: string
  model_family: string
  reference_model_id: number | null
}

const WATERTIGHT_STEP_TASKS = [
  'import_geometry',
  'add_local_sizing',
  'create_surface_mesh',
  'describe_geometry',
  'update_regions',
  'add_boundary_layer',
  'create_volume_mesh',
] as const

const buildInitialChildInstances = (tasks: MeshingSchemaTask[]): MeshingChildInstanceMap => {
  const result: MeshingChildInstanceMap = {}
  const boundaryLayer = tasks.find((task) => task.python_name === 'add_boundary_layer')
  if (boundaryLayer?.child_template) {
    const name = defaultChildName(boundaryLayer, 1)
    result[taskPathKey(['add_boundary_layer'])] = [{ id: name, name }]
  }
  return result
}

const buildInitialValues = (
  tasks: MeshingSchemaTask[],
  childInstances: MeshingChildInstanceMap,
  contract: MeshingWorkflowContract | null,
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
  for (const step of contract?.steps ?? []) {
    for (const field of step.fields) {
      if (field.ui_default_override !== undefined) {
        result[selectionKey(step.task_path, null, field.path)] =
          field.ui_default_override as MeshingPresetValue
      }
    }
  }
  return result
}

interface EditorStateProps {
  included: MeshingIncludedMap
  values: MeshingValueMap
  showDeveloper: boolean
  lengthUnit: string
  onPickFile?: () => Promise<void>
  onToggle: (key: string, checked: boolean) => void
  onValueChange: (key: string, value: MeshingPresetValue) => void
}

let childInstanceCounter = 0

const nextChildInstanceId = (task: MeshingSchemaTask): string => {
  childInstanceCounter += 1
  return `${task.python_name}-${childInstanceCounter}`
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

const restoreEditorState = (
  tasks: MeshingSchemaTask[],
  contract: MeshingWorkflowContract | null,
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
      })
      childInstances[key] = instances
    }
  }

  const values = buildInitialValues(tasks, childInstances, contract)
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
    included[key] = true
    values[key] = item.value
  }

  return { childInstances, included, values }
}

function LabelSelectionControl({
  argument,
  value,
  disabled,
  onChange,
}: {
  argument: MeshingSchemaArgument
  value: MeshingPresetValue
  disabled: boolean
  onChange: (value: MeshingPresetValue) => void
}) {
  const { t } = useTranslation()
  const [filterText, setFilterText] = useState('')
  const selected = Array.isArray(value) ? value.map(String) : []
  const available = Array.from(
    new Set([...(argument.allowed_values ?? []).map(String), ...selected]),
  )
  const filtered = available.filter((item) =>
    item.toLowerCase().includes(filterText.trim().toLowerCase()),
  )
  return (
    <Space direction="vertical" size={6} className="full-width">
      <Space wrap>
        <Input
          value={filterText}
          allowClear
          disabled={disabled}
          placeholder={t('meshing.filterText')}
          onChange={(event) => setFilterText(event.target.value)}
          className="meshing-label-filter"
        />
        <Tag>
          {selected.length}/{available.length}
        </Tag>
        <Button size="small" disabled={disabled} onClick={() => onChange(available)}>
          {t('meshing.selectAll')}
        </Button>
        <Button size="small" disabled={disabled} onClick={() => onChange(filtered)}>
          {t('meshing.selectChecked')}
        </Button>
        <Button
          size="small"
          disabled={disabled}
          onClick={() => onChange(available.filter((item) => !selected.includes(item)))}
        >
          {t('meshing.invertSelection')}
        </Button>
      </Space>
      <Select
        mode="tags"
        value={selected}
        disabled={disabled}
        options={available.map((item) => ({ value: item, label: item }))}
        onChange={(next) => onChange(next)}
        tokenSeparators={[',']}
        className="full-width"
      />
    </Space>
  )
}

export function ArgumentControl({
  argument,
  value,
  disabled,
  onChange,
}: {
  argument: MeshingSchemaArgument
  value: MeshingPresetValue
  disabled: boolean
  onChange: (value: MeshingPresetValue) => void
}) {
  const localizedOption = (option: string): string => {
    return localizedAnsysValue(option)
  }

  if (
    ['setup_type', 'wall_to_internal', 'invoke_share_topology', 'multizone'].includes(
      argument.name,
    ) &&
    argument.allowed_values?.length
  ) {
    return (
      <Radio.Group
        value={String(value)}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as string)}
        options={argument.allowed_values.map((option) => ({
          value: String(option),
          label: localizedOption(String(option)),
        }))}
      />
    )
  }

  if (['boi_face_label_list', 'bl_label_list', 'zone_selection_list'].includes(argument.name)) {
    return (
      <LabelSelectionControl
        argument={argument}
        value={value}
        disabled={disabled}
        onChange={onChange}
      />
    )
  }

  if (argument.value_type === 'bool') {
    return <Switch checked={Boolean(value)} disabled={disabled} onChange={onChange} />
  }

  if (argument.allowed_values?.length) {
    const options = argument.allowed_values.map((item) => ({
      value: String(item),
      label: localizedAnsysValue(String(item)),
    }))
    if (argument.value_type === 'list' || argument.value_type === 'RepeatedScalarContainer') {
      const selected = Array.isArray(value) ? value.map(String) : []
      return (
        <Select
          mode="multiple"
          value={selected}
          disabled={disabled}
          options={options}
          onChange={(next) =>
            onChange(
              next.map(
                (entry) => argument.allowed_values?.find((item) => String(item) === entry) ?? entry,
              ),
            )
          }
          className="full-width"
        />
      )
    }
    return (
      <Select
        value={String(value)}
        disabled={disabled}
        options={options}
        onChange={(next) =>
          onChange(argument.allowed_values?.find((item) => String(item) === next) ?? next)
        }
        className="full-width"
      />
    )
  }

  if (argument.value_type === 'list' || argument.value_type === 'RepeatedScalarContainer') {
    return (
      <Select
        mode="tags"
        value={Array.isArray(value) ? value.map(String) : []}
        disabled={disabled}
        onChange={(next) => onChange(next)}
        className="full-width"
        tokenSeparators={[',']}
      />
    )
  }

  if (argument.value_type === 'object') {
    return (
      <Input.TextArea
        rows={3}
        disabled={disabled}
        value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
        onChange={(event) => {
          try {
            onChange(JSON.parse(event.target.value) as MeshingPresetValue)
          } catch {
            onChange(event.target.value)
          }
        }}
      />
    )
  }

  if (argument.value_type === 'int' || argument.value_type === 'float') {
    return (
      <InputNumber
        value={typeof value === 'number' ? value : null}
        disabled={disabled}
        step={argument.value_type === 'int' ? 1 : 0.0001}
        precision={argument.value_type === 'int' ? 0 : undefined}
        onChange={(next) => onChange(next ?? 0)}
        className="full-width"
      />
    )
  }

  return (
    <Input
      value={typeof value === 'string' ? value : value == null ? '' : String(value)}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}

function ArgumentSections({
  task,
  taskPath,
  childInstanceId,
  included,
  values,
  showDeveloper,
  lengthUnit,
  onPickFile,
  onToggle,
  onValueChange,
}: EditorStateProps & {
  task: MeshingSchemaTask
  taskPath: string[]
  childInstanceId: string | null
}) {
  const { t, i18n } = useTranslation()
  const sourceArguments =
    childInstanceId === null ? task.arguments : (task.child_template?.arguments ?? [])
  const leaves = flattenArgumentLeaves(sourceArguments).filter(
    (leaf) => childInstanceId === null || !isManagedChildArgument(task, leaf.argument),
  )
  const visibleLeaves = leaves.filter(
    (leaf) => showDeveloper || !isDeveloperArgument(leaf.argument),
  )
  const primaryLeaves = visibleLeaves.filter(
    (leaf) => !isAdvancedArgument(leaf.argument) && !isDeveloperArgument(leaf.argument),
  )
  const advancedLeaves = visibleLeaves.filter((leaf) => isAdvancedArgument(leaf.argument))
  const developerLeaves = showDeveloper
    ? leaves.filter((leaf) => isDeveloperArgument(leaf.argument))
    : []

  const renderLeaf = (leaf: MeshingArgumentLeaf) => {
    const key = selectionKey(taskPath, childInstanceId, leaf.argumentPath)
    const editable = leaf.argument.editable !== false && leaf.argument.read_only !== true
    const current = values[key] ?? defaultArgumentValue(leaf.argument)
    const technicalPath = leaf.argumentPath.join(' > ')
    const displayPath = leaf.displayPath.map((part) => localizedAnsysTerm(part)).join(' > ')
    const unitSuffix = leaf.argument.display_unit?.includes('LengthUnit') ? ` [${lengthUnit}]` : ''
    return (
      <div key={key} className={`meshing-argument-row ${included[key] ? 'is-included' : ''}`}>
        <Checkbox
          checked={Boolean(included[key])}
          disabled={!editable}
          onChange={(event) => onToggle(key, event.target.checked)}
        >
          <Space direction="vertical" size={2}>
            <Typography.Text strong>
              {displayPath}
              {unitSuffix}
            </Typography.Text>
            {i18n.language.startsWith('en') || showDeveloper ? (
              <Typography.Text type="secondary" className="meshing-argument-path">
                {displayPath === technicalPath ? leaf.argument.edit_path : technicalPath}
                {showDeveloper && leaf.argument.display_condition
                  ? ` · ${t('meshing.conditionLabel')}：${leaf.argument.display_condition}`
                  : ''}
              </Typography.Text>
            ) : null}
          </Space>
        </Checkbox>
        <div className="meshing-argument-control">
          {leaf.argument.name === 'file_name' && onPickFile ? (
            <Space.Compact className="full-width">
              <Input
                value={typeof current === 'string' ? current : ''}
                disabled={!editable || !included[key]}
                onChange={(event) => onValueChange(key, event.target.value)}
              />
              <Button onClick={() => void onPickFile()}>{t('meshing.browse')}</Button>
            </Space.Compact>
          ) : (
            <ArgumentControl
              argument={leaf.argument}
              value={current}
              disabled={!editable || !included[key]}
              onChange={(value) => onValueChange(key, value)}
            />
          )}
        </div>
      </div>
    )
  }

  if (leaves.length === 0) {
    const error = task.arguments.find((argument) => argument.name === '<arguments>')?.error
    return error ? <Alert type="warning" showIcon message={error} /> : null
  }

  return (
    <Space direction="vertical" size={14} className="full-width">
      {primaryLeaves.length > 0 ? (
        <Space direction="vertical" size={10} className="full-width">
          {primaryLeaves.map(renderLeaf)}
        </Space>
      ) : null}
      {advancedLeaves.length > 0 ? (
        <Collapse
          className="advanced-options-collapse"
          items={[
            {
              key: 'advanced',
              label: `${t('meshing.advancedOptions')} (${advancedLeaves.length})`,
              children: (
                <Space direction="vertical" size={10} className="full-width">
                  {advancedLeaves.map(renderLeaf)}
                </Space>
              ),
            },
          ]}
        />
      ) : null}
      {developerLeaves.length > 0 ? (
        <Collapse
          className="advanced-options-collapse"
          items={[
            {
              key: 'developer',
              label: t('meshing.developerOptions', { count: developerLeaves.length }),
              children: (
                <Space direction="vertical" size={10} className="full-width">
                  {developerLeaves.map(renderLeaf)}
                </Space>
              ),
            },
          ]}
        />
      ) : null}
    </Space>
  )
}

function WorkflowStepper({
  steps,
  activeStepKey,
  completedSteps,
  onSelectStep,
}: {
  steps: MeshingSchemaTask[]
  activeStepKey: string
  completedSteps: Set<string>
  onSelectStep: (task: MeshingSchemaTask) => void
}) {
  const { t } = useTranslation()

  return (
    <div
      className="meshing-stepper-scroll"
      role="navigation"
      aria-label={t('meshing.workflowSteps')}
    >
      <div className="meshing-stepper">
        {steps.map((task) => {
          const isActive = task.python_name === activeStepKey
          const isComplete = completedSteps.has(task.python_name)
          return (
            <div
              key={task.python_name}
              className={`meshing-step ${isActive ? 'is-active' : ''} ${isComplete ? 'is-complete' : ''}`}
            >
              <button
                type="button"
                className="meshing-step-main"
                onClick={() => onSelectStep(task)}
                aria-current={isActive ? 'step' : undefined}
              >
                <span className="meshing-step-icon" aria-hidden="true">
                  <ThunderboltOutlined />
                </span>
                <span className="meshing-step-copy">
                  <strong>{localizedMeshingTaskName(t, task)}</strong>
                </span>
                {isComplete ? (
                  <CheckOutlined
                    className="meshing-step-check"
                    aria-label={t('meshing.completed')}
                  />
                ) : null}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface RegionRow {
  id: string
  name: string
  type: string
}

function RegionTableEditor({
  task,
  values,
  onToggle,
  onValueChange,
}: Pick<EditorStateProps, 'values' | 'onToggle' | 'onValueChange'> & {
  task: MeshingSchemaTask
}) {
  const { t } = useTranslation()
  const taskPath = [task.python_name]
  const nameKey = selectionKey(taskPath, null, ['region_name_list'])
  const typeKey = selectionKey(taskPath, null, ['region_type_list'])
  const rawNames = values[nameKey]
  const rawTypes = values[typeKey]
  const names = Array.isArray(rawNames) ? rawNames.map(String) : []
  const types = Array.isArray(rawTypes) ? rawTypes.map(String) : []
  const [filterType, setFilterType] = useState<'all' | 'fluid' | 'solid'>('all')
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const rows: RegionRow[] = names.map((name, index) => ({
    id: `${index}:${name}`,
    name,
    type: types[index] ?? 'fluid',
  }))
  const commit = (next: RegionRow[]): void => {
    onValueChange(
      nameKey,
      next.map((row) => row.name),
    )
    onValueChange(
      typeKey,
      next.map((row) => row.type),
    )
    onToggle(nameKey, true)
    onToggle(typeKey, true)
  }
  const visibleRows = rows.filter((row) => {
    const typeMatch = filterType === 'all' || row.type === filterType
    const textMatch = !search.trim() || row.name.toLowerCase().includes(search.toLowerCase())
    return typeMatch && textMatch
  })
  const visibleIds = visibleRows.map((row) => row.id)
  const selectVisible = (): void => setSelectedIds(new Set(visibleIds))
  const invertSelection = (): void =>
    setSelectedIds(new Set(rows.filter((row) => !selectedIds.has(row.id)).map((row) => row.id)))

  return (
    <Space direction="vertical" size={12} className="full-width">
      <Space wrap>
        <Select
          value={filterType}
          onChange={setFilterType}
          options={[
            { value: 'all', label: localizedAnsysValue('All') },
            { value: 'fluid', label: localizedAnsysValue('fluid') },
            { value: 'solid', label: localizedAnsysValue('solid') },
          ]}
        />
        <Input.Search
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          allowClear
          placeholder={t('meshing.filterText')}
          className="log-search"
        />
        <Button onClick={() => setSelectedIds(new Set(rows.map((row) => row.id)))}>
          {t('meshing.selectAll')}
        </Button>
        <Button onClick={selectVisible}>{t('meshing.selectChecked')}</Button>
        <Button onClick={invertSelection}>{t('meshing.invertSelection')}</Button>
        <Button
          type="dashed"
          icon={<PlusOutlined />}
          onClick={() => commit([...rows, { id: `new:${rows.length}`, name: '', type: 'fluid' }])}
        >
          {t('meshing.addRegion')}
        </Button>
      </Space>
      <Table<RegionRow>
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={visibleRows}
        rowSelection={{
          selectedRowKeys: [...selectedIds],
          onChange: (keys) => setSelectedIds(new Set(keys.map(String))),
        }}
        columns={[
          {
            title: localizedAnsysTerm('Region Name'),
            dataIndex: 'name',
            key: 'name',
            render: (_value, row) => (
              <Input
                value={row.name}
                placeholder={localizedAnsysTerm('Region Name')}
                onChange={(event) =>
                  commit(
                    rows.map((item) =>
                      item.id === row.id ? { ...item, name: event.target.value } : item,
                    ),
                  )
                }
              />
            ),
          },
          {
            title: localizedAnsysTerm('Region Type'),
            dataIndex: 'type',
            key: 'type',
            render: (_value, row) => (
              <Select
                value={row.type}
                aria-label={localizedAnsysTerm('Region Type')}
                options={[
                  { value: 'fluid', label: localizedAnsysValue('fluid') },
                  { value: 'solid', label: localizedAnsysValue('solid') },
                ]}
                onChange={(value) =>
                  commit(rows.map((item) => (item.id === row.id ? { ...item, type: value } : item)))
                }
              />
            ),
          },
          {
            title: '',
            key: 'actions',
            width: 60,
            render: (_value, row) => (
              <Button
                danger
                type="text"
                icon={<DeleteOutlined />}
                onClick={() => commit(rows.filter((item) => item.id !== row.id))}
              />
            ),
          },
        ]}
      />
    </Space>
  )
}

function WorkflowStepPanel({
  task,
  childInstances,
  onAddChild,
  onRemoveChild,
  onRenameChild,
  ...editorProps
}: EditorStateProps & {
  task: MeshingSchemaTask
  childInstances: MeshingChildInstanceMap
  onAddChild: (task: MeshingSchemaTask, taskPath: string[]) => void
  onRemoveChild: (taskPath: string[], instanceId: string) => void
  onRenameChild: (taskPath: string[], instanceId: string, name: string) => void
}) {
  const { t } = useTranslation()
  const taskPath = [task.python_name]
  const instancesKey = taskPathKey(taskPath)
  const hasChildTemplate = Boolean(task.supports_child_template && task.child_template)
  const instances = childInstances[instancesKey] ?? []
  const managedNameArgument = childNameArgument(task)
  const toggleArgument = task.arguments.find((argument) => argument.name === 'add_child')
  const toggleKey = selectionKey(taskPath, null, ['add_child'])
  const toggleValue = String(
    editorProps.values[toggleKey] ?? (toggleArgument ? defaultArgumentValue(toggleArgument) : 'no'),
  )
  const showChildren = toggleValue.toLowerCase().startsWith('yes')

  if (task.python_name === 'update_regions') {
    return (
      <Space direction="vertical" size={14} className="full-width">
        <RegionTableEditor
          task={task}
          values={editorProps.values}
          onToggle={editorProps.onToggle}
          onValueChange={editorProps.onValueChange}
        />
        {editorProps.showDeveloper ? (
          <ArgumentSections
            task={task}
            taskPath={taskPath}
            childInstanceId={null}
            {...editorProps}
          />
        ) : null}
      </Space>
    )
  }

  if (!hasChildTemplate) {
    return (
      <Space direction="vertical" size={14} className="full-width">
        {task.task_type === 'Compound' && task.child_template_error ? (
          <Alert type="warning" showIcon message={task.child_template_error} />
        ) : null}
        <ArgumentSections task={task} taskPath={taskPath} childInstanceId={null} {...editorProps} />
      </Space>
    )
  }

  return (
    <Space direction="vertical" size={14} className="full-width">
      {toggleArgument ? (
        <div className="meshing-argument-row is-included">
          <Typography.Text strong>
            {localizedAnsysTerm(
              toggleArgument.display_name ?? toggleArgument.name,
              toggleArgument.name,
            )}
          </Typography.Text>
          <div className="meshing-argument-control">
            <Select
              value={toggleValue}
              aria-label={localizedAnsysTerm(
                toggleArgument.display_name ?? toggleArgument.name,
                toggleArgument.name,
              )}
              className="full-width"
              options={(toggleArgument.allowed_values ?? ['yes', 'no']).map((value) => ({
                value: String(value),
                label: localizedAnsysValue(String(value)),
              }))}
              onChange={(next) => {
                editorProps.onValueChange(toggleKey, next)
                editorProps.onToggle(toggleKey, true)
                if (next.toLowerCase().startsWith('yes') && instances.length === 0) {
                  onAddChild(task, taskPath)
                }
              }}
            />
          </div>
        </div>
      ) : null}
      {task.child_template_warning ? (
        <Alert type="warning" showIcon message={t('meshing.childTemplateFallback')} />
      ) : null}
      {showChildren ? (
        <Space wrap>
          <Button type="dashed" icon={<PlusOutlined />} onClick={() => onAddChild(task, taskPath)}>
            {t('meshing.addChildInstance')}
          </Button>
          <Typography.Text type="secondary">{t('meshing.childInstanceHint')}</Typography.Text>
        </Space>
      ) : null}
      {showChildren && instances.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('meshing.noChildInstances')} />
      ) : null}
      {showChildren
        ? instances.map((instance) => (
            <Card
              key={instance.id}
              size="small"
              title={instance.name}
              extra={
                <Button
                  danger
                  type="text"
                  icon={<DeleteOutlined />}
                  aria-label={t('meshing.removeChildInstance')}
                  onClick={() => onRemoveChild(taskPath, instance.id)}
                />
              }
            >
              <Space direction="vertical" size={14} className="full-width">
                <Form.Item
                  label={t('meshing.childInstanceName')}
                  required
                  className="meshing-child-name-field"
                >
                  <Input
                    value={instance.name}
                    placeholder={t('meshing.childInstanceNamePlaceholder')}
                    onChange={(event) => onRenameChild(taskPath, instance.id, event.target.value)}
                  />
                </Form.Item>
                {managedNameArgument ? (
                  <Typography.Text type="secondary">
                    {t('meshing.managedChildName', { argument: managedNameArgument.name })}
                  </Typography.Text>
                ) : null}
                <ArgumentSections
                  task={task}
                  taskPath={taskPath}
                  childInstanceId={instance.id}
                  {...editorProps}
                />
              </Space>
            </Card>
          ))
        : null}
    </Space>
  )
}

export function MeshingAutomationCreatePage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const editMatch = useMatch('/meshing/:id/edit')
  const sourceAutomationId = Number(editMatch?.params.id ?? 0)
  const isEditing = sourceAutomationId > 0
  const pageTitle = isEditing ? t('meshing.editTitle') : t('meshing.createTitle')
  const pageDescription = isEditing ? t('meshing.editDescription') : t('meshing.createDescription')
  const [form] = Form.useForm<MeshingFormValues>()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [workflowType, setWorkflowType] = useState<MeshingWorkflowType>('watertight')
  const [reloadVersion, setReloadVersion] = useState(0)
  const [sourceAutomation, setSourceAutomation] = useState<MeshingAutomation | null>(null)
  const [schema, setSchema] = useState<MeshingWorkflowSchema | null>(null)
  const [workflowContract, setWorkflowContract] = useState<MeshingWorkflowContract | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [included, setIncluded] = useState<MeshingIncludedMap>({})
  const [values, setValues] = useState<MeshingValueMap>({})
  const [childInstances, setChildInstances] = useState<MeshingChildInstanceMap>({})
  const [activeStepKey, setActiveStepKey] = useState<string>('import_geometry')
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())
  const [showDeveloper, setShowDeveloper] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [stepRunning, setStepRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (sidecarState !== 'ready') return
    if (!isEditing) {
      return
    }

    let active = true
    void fluentAiService.meshingAutomations
      .get(sourceAutomationId)
      .then((automation) => {
        if (!active) return
        setSourceAutomation(automation)
        setWorkflowType(automation.preset.workflow_type)
      })
      .catch((loadError: unknown) => {
        if (!active) return
        setError(loadError instanceof Error ? loadError.message : String(loadError))
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [isEditing, reloadVersion, sidecarState, sourceAutomationId])

  useEffect(() => {
    if (sidecarState !== 'ready') return
    if (isEditing && sourceAutomation === null) return
    let active = true
    void Promise.all([
      fluentAiService.meshing.schema(workflowType),
      fluentAiService.models.list(),
      workflowType === 'watertight'
        ? fluentAiService.meshing.workflowSchema('watertight')
        : Promise.resolve(null),
    ])
      .then(([nextSchema, nextModels, nextContract]) => {
        if (!active) return
        setSchema(nextSchema)
        setWorkflowContract(nextContract)
        setModels(nextModels)
        if (isEditing && sourceAutomation) {
          const restored = restoreEditorState(
            nextSchema.tasks,
            nextContract,
            sourceAutomation.preset.items,
          )
          setChildInstances(restored.childInstances)
          setValues(restored.values)
          setIncluded(restored.included)
        } else {
          const initialChildren =
            workflowType === 'watertight' ? buildInitialChildInstances(nextSchema.tasks) : {}
          setChildInstances(initialChildren)
          setValues(buildInitialValues(nextSchema.tasks, initialChildren, nextContract))
          setIncluded({})
        }
        setCompletedSteps(new Set())
        setActiveStepKey(
          workflowType === 'watertight'
            ? WATERTIGHT_STEP_TASKS[0]
            : (nextSchema.tasks[0]?.python_name ?? ''),
        )
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : String(loadError))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [isEditing, sidecarState, sourceAutomation, workflowType, reloadVersion])

  useEffect(() => {
    if (!isEditing || !sourceAutomation || loading || schema === null) return
    form.setFieldsValue({
      name: sourceAutomation.name,
      description: sourceAutomation.description,
      model_family: sourceAutomation.model_family,
      reference_model_id: sourceAutomation.reference_model_id,
    })
  }, [form, isEditing, loading, schema, sourceAutomation])

  const lengthUnit = String(
    values[selectionKey(['import_geometry'], null, ['length_unit'])] ?? 'mm',
  )

  const workflowSteps = useMemo(() => {
    const tasks = schema?.tasks ?? []
    if (workflowType !== 'watertight') return tasks
    const byName = new Map(tasks.map((task) => [task.python_name, task]))
    const stepOrder = workflowContract?.step_order ?? WATERTIGHT_STEP_TASKS
    return stepOrder
      .map((name) => byName.get(name))
      .filter((task): task is MeshingSchemaTask => task !== undefined)
  }, [schema, workflowType, workflowContract])

  const selectedCount = useMemo(
    () =>
      workflowSteps.filter((task) =>
        Object.entries(included).some(([key, selected]) => {
          if (!selected) return false
          try {
            const parsed = JSON.parse(key) as unknown[]
            return (
              Array.isArray(parsed) && Array.isArray(parsed[0]) && parsed[0][0] === task.python_name
            )
          } catch {
            return false
          }
        }),
      ).length,
    [included, workflowSteps],
  )

  const activeTask =
    workflowSteps.find((task) => task.python_name === activeStepKey) ?? workflowSteps[0] ?? null

  const selectStep = (task: MeshingSchemaTask): void => {
    setActiveStepKey(task.python_name)
  }

  const toggle = (key: string, checked: boolean) =>
    setIncluded((current) => ({ ...current, [key]: checked }))
  const changeValue = (key: string, value: MeshingPresetValue) =>
    setValues((current) => ({ ...current, [key]: value }))

  const pickGeometryFile = async (): Promise<void> => {
    try {
      const picked = await fluentAiService.models.pickFile()
      if (!picked) return
      const key = selectionKey(['import_geometry'], null, ['file_name'])
      changeValue(key, picked.filePath)
      toggle(key, true)
    } catch (pickError) {
      message.error(pickError instanceof Error ? pickError.message : String(pickError))
    }
  }

  const addChild = (task: MeshingSchemaTask, taskPath: string[]) => {
    if (!task.child_template) return
    const key = taskPathKey(taskPath)
    const current = childInstances[key] ?? []
    const instance: MeshingChildInstance = {
      id: nextChildInstanceId(task),
      name: defaultChildName(task, current.length + 1),
    }
    setChildInstances((state) => ({ ...state, [key]: [...(state[key] ?? []), instance] }))
    setValues((state) => {
      const next = { ...state }
      for (const leaf of flattenArgumentLeaves(task.child_template?.arguments ?? [])) {
        if (isManagedChildArgument(task, leaf.argument)) continue
        next[selectionKey(taskPath, instance.id, leaf.argumentPath)] = defaultArgumentValue(
          leaf.argument,
        )
      }
      return next
    })
  }

  const removeChild = (taskPath: string[], instanceId: string) => {
    const key = taskPathKey(taskPath)
    setChildInstances((state) => ({
      ...state,
      [key]: (state[key] ?? []).filter((instance) => instance.id !== instanceId),
    }))
    const belongsToRemovedChild = (selection: string): boolean => {
      try {
        const parsed = JSON.parse(selection) as unknown[]
        return Array.isArray(parsed) && parsed[1] === instanceId
      } catch {
        return false
      }
    }
    setIncluded((state) =>
      Object.fromEntries(Object.entries(state).filter(([key]) => !belongsToRemovedChild(key))),
    )
    setValues((state) =>
      Object.fromEntries(Object.entries(state).filter(([key]) => !belongsToRemovedChild(key))),
    )
  }

  const renameChild = (taskPath: string[], instanceId: string, name: string) => {
    const key = taskPathKey(taskPath)
    setChildInstances((state) => ({
      ...state,
      [key]: (state[key] ?? []).map((instance) =>
        instance.id === instanceId ? { ...instance, name } : instance,
      ),
    }))
  }

  const reload = () => {
    setLoading(true)
    setError(null)
    setSchema(null)
    if (isEditing) {
      setSourceAutomation(null)
    }
    setReloadVersion((version) => version + 1)
  }

  const reportIssues = (issues: ReturnType<typeof buildMeshingPresetItems>['issues']): void => {
    const messages = issues.map((issue) => {
      if (issue.code === 'childNameRequired') {
        return t('meshing.childNameRequired', { task: issue.taskName })
      }
      if (issue.code === 'duplicateChildName') {
        return t('meshing.duplicateChildName', {
          task: issue.taskName,
          name: issue.childName ?? '',
        })
      }
      return t('meshing.childHasNoSelection', {
        task: issue.taskName,
        name: issue.childName ?? '',
      })
    })
    void message.error([...new Set(messages)].join('; '))
  }

  const executeActiveStep = async (): Promise<void> => {
    if (!activeTask) return
    const { items, issues } = buildMeshingPresetItems(
      [activeTask],
      included,
      values,
      childInstances,
    )
    if (issues.length > 0) {
      reportIssues(issues)
      return
    }
    if (items.length === 0) {
      message.warning(t('meshing.noStepItems'))
      return
    }
    setStepRunning(true)
    try {
      const report = await fluentAiService.meshing.write({
        workflow_type: workflowType,
        items,
        verify: true,
        create_compound_child: true,
      })
      if (report.status !== 'success') {
        throw new Error(report.error ?? t('settings.meshingDiagnosticFailed'))
      }
      setCompletedSteps((current) => new Set(current).add(activeTask.python_name))
      message.success(t('meshing.stepVerified'))
    } catch (stepError) {
      message.error(stepError instanceof Error ? stepError.message : String(stepError))
    } finally {
      setStepRunning(false)
    }
  }

  const restoreActiveStep = (): void => {
    if (!activeTask) return
    const defaults = buildInitialValues([activeTask], childInstances, workflowContract)
    setValues((current) => ({ ...current, ...defaults }))
    const belongsToActiveTask = (key: string): boolean => {
      try {
        const parsed = JSON.parse(key) as unknown[]
        return (
          Array.isArray(parsed) &&
          Array.isArray(parsed[0]) &&
          parsed[0][0] === activeTask.python_name
        )
      } catch {
        return false
      }
    }
    setIncluded((current) =>
      Object.fromEntries(Object.entries(current).filter(([key]) => !belongsToActiveTask(key))),
    )
    setCompletedSteps((current) => {
      const next = new Set(current)
      next.delete(activeTask.python_name)
      return next
    })
  }

  const save = async (formValues: MeshingFormValues): Promise<void> => {
    if (!schema) return
    const { items, issues } = buildMeshingPresetItems(
      schema.tasks,
      included,
      values,
      childInstances,
    )
    if (issues.length > 0) {
      reportIssues(issues)
      return
    }
    if (items.length === 0) {
      message.warning(t('meshing.selectAtLeastOne'))
      return
    }
    const preset: MeshingPresetDocument = {
      schema_version: 1,
      fluent_version: schema.fluent_version,
      workflow_type: workflowType,
      items,
    }
    setSaving(true)
    try {
      const validation = await fluentAiService.meshing.validatePreset(preset)
      if (!validation.valid) {
        message.error(validation.errors.join('; '))
        return
      }
      const payload = {
        name: formValues.name,
        description: formValues.description ?? '',
        model_family: formValues.model_family ?? '',
        reference_model_id: formValues.reference_model_id ?? null,
        preset,
        status: sourceAutomation?.status ?? 'draft',
      } as const
      if (isEditing) {
        await fluentAiService.meshingAutomations.update(sourceAutomationId, payload)
        message.success(t('meshing.updated'))
      } else {
        await fluentAiService.meshingAutomations.create(payload)
        message.success(t('meshing.created'))
      }
      navigate('/meshing')
    } catch (saveError) {
      message.error(saveError instanceof Error ? saveError.message : String(saveError))
    } finally {
      setSaving(false)
    }
  }

  if (sidecarState === 'error') {
    return (
      <PageContent title={pageTitle} description={pageDescription}>
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={t('errors.sidecarErrorDescription')}
          retryLabel={t('common.reload')}
        />
      </PageContent>
    )
  }

  return (
    <PageContent
      title={pageTitle}
      description={pageDescription}
      actions={
        <Space wrap>
          <Tag color="blue">{t('meshing.selectedOptions', { count: selectedCount })}</Tag>
          <Segmented
            value={workflowType}
            disabled={isEditing}
            onChange={(value) => {
              setLoading(true)
              setError(null)
              setSchema(null)
              setWorkflowType(value as MeshingWorkflowType)
            }}
            options={[
              { value: 'watertight', label: t('meshing.watertight') },
              { value: 'fault-tolerant', label: t('meshing.faultTolerant') },
            ]}
          />
        </Space>
      }
    >
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          title={t('meshing.schemaError')}
          description={error}
          retryLabel={t('common.reload')}
          onRetry={reload}
        />
      ) : (
        <Card>
          <Form<MeshingFormValues>
            form={form}
            layout="vertical"
            initialValues={{
              name: '',
              description: '',
              model_family: '',
              reference_model_id: null,
            }}
            onFinish={(formValues) => void save(formValues)}
          >
            <Space align="start" wrap>
              <Form.Item
                name="name"
                label={t('pages.automationCreate.name')}
                rules={[{ required: true }]}
                className="meshing-name-field"
              >
                <Input maxLength={120} />
              </Form.Item>
              <Form.Item
                name="model_family"
                label={t('meshing.modelFamily')}
                className="meshing-family-field"
              >
                <Input maxLength={200} placeholder={t('meshing.modelFamilyPlaceholder')} />
              </Form.Item>
              <Form.Item
                name="reference_model_id"
                label={t('meshing.referenceModel')}
                className="meshing-model-field"
              >
                <Select
                  allowClear
                  options={models.map((model) => ({ value: model.id, label: model.name }))}
                  placeholder={t('meshing.referenceModelPlaceholder')}
                />
              </Form.Item>
            </Space>
            <Form.Item name="description" label={t('pages.automationCreate.descriptionField')}>
              <Input.TextArea rows={2} maxLength={2_000} />
            </Form.Item>
            <Space align="center" wrap>
              <Typography.Title level={5} style={{ margin: 0 }}>
                {t('meshing.workflowOptions')}
              </Typography.Title>
              <Space size={6}>
                <Switch checked={showDeveloper} onChange={setShowDeveloper} />
                <Typography.Text type="secondary">
                  {t('meshing.showDeveloperOptions')}
                </Typography.Text>
              </Space>
            </Space>
            <WorkflowStepper
              steps={workflowSteps}
              activeStepKey={activeTask?.python_name ?? ''}
              completedSteps={completedSteps}
              onSelectStep={selectStep}
            />
            {activeTask ? (
              <Card
                className="meshing-step-panel"
                title={
                  <Space wrap>
                    <span>{localizedMeshingTaskName(t, activeTask)}</span>
                    <Typography.Text type="secondary" className="task-type-label">
                      {localizedMeshingTaskType(t, activeTask.task_type)}
                    </Typography.Text>
                  </Space>
                }
              >
                <WorkflowStepPanel
                  task={activeTask}
                  childInstances={childInstances}
                  included={included}
                  values={values}
                  showDeveloper={showDeveloper}
                  lengthUnit={lengthUnit}
                  onPickFile={pickGeometryFile}
                  onToggle={toggle}
                  onValueChange={changeValue}
                  onAddChild={addChild}
                  onRemoveChild={removeChild}
                  onRenameChild={renameChild}
                />
                <Space wrap className="meshing-step-actions">
                  {activeTask.python_name === 'update_regions' ? (
                    <Button onClick={() => message.info(t('meshing.previewUnavailable'))}>
                      {t('meshing.printSummary')}
                    </Button>
                  ) : null}
                  <Button
                    type="primary"
                    loading={stepRunning}
                    onClick={() => void executeActiveStep()}
                  >
                    {localizedMeshingTaskName(t, activeTask)}
                  </Button>
                  <Button onClick={restoreActiveStep}>{t('meshing.restoreEdit')}</Button>
                  {['add_local_sizing', 'create_surface_mesh'].includes(activeTask.python_name) ? (
                    <Button onClick={() => message.info(t('meshing.previewUnavailable'))}>
                      {t('meshing.clearPreview')}
                    </Button>
                  ) : null}
                  {activeTask.python_name === 'import_geometry' ||
                  activeTask.python_name === 'add_local_sizing' ? (
                    <Button onClick={() => message.info(t('meshing.previewUnavailable'))}>
                      {t('meshing.drawGeometry')}
                    </Button>
                  ) : null}
                  {['update_regions', 'add_boundary_layer'].includes(activeTask.python_name) ? (
                    <Button onClick={() => message.info(t('meshing.previewUnavailable'))}>
                      {t('meshing.drawRegions')}
                    </Button>
                  ) : null}
                </Space>
              </Card>
            ) : null}
            <Form.Item className="form-actions">
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={saving}
                aria-label={isEditing ? t('meshing.updateAutomation') : t('meshing.save')}
              >
                {saving
                  ? t('pages.automationCreate.saving')
                  : isEditing
                    ? t('meshing.updateAutomation')
                    : t('meshing.save')}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={reload} className="reload-meshing">
                {t('common.reload')}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      )}
    </PageContent>
  )
}
