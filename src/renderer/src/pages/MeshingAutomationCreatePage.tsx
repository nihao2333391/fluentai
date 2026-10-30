import {
  CheckOutlined,
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useMatch, useNavigate } from 'react-router-dom'

import type {
  MeshingAutomation,
  MeshingPresetDocument,
  MeshingPresetValue,
  MeshingSchemaArgument,
  MeshingSchemaTask,
  MeshingWorkflowContract,
  MeshingWorkflowSchema,
  MeshingWorkflowType,
  Model,
  PartCategory,
} from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { TemplateAgentPanel } from '../components/TemplateAgentPanel'
import { localizedAnsysTerm, localizedAnsysValue } from '../i18n/ansysLabels'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'
import {
  buildInitialValues,
  buildMeshingPresetItems,
  childNameArgument,
  collectFaceLabels,
  defaultArgumentValue,
  defaultChildName,
  flattenArgumentLeaves,
  isAdvancedArgument,
  isArgumentConditionVisible,
  isDeveloperArgument,
  isManagedChildArgument,
  nextChildInstanceId,
  restoreEditorState,
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
  'apply_share_topology',
  'enclose_fluid_regions',
  'update_boundaries',
  'create_regions',
  'update_regions',
  'add_boundary_layer',
  'create_volume_mesh',
] as const

const LOCAL_SIZING_MAIN_CONTROLS = new Set([
  'edge_label_list',
  'edge_zone_list',
  'reverse_edge_zone_orientation',
  'reverse_edge_zone_list',
  'boi_patchingtoggle',
  'draw_size_control',
])

const buildInitialChildInstances = (tasks: MeshingSchemaTask[]): MeshingChildInstanceMap => {
  const result: MeshingChildInstanceMap = {}
  for (const name of ['add_boundary_layer', 'enclose_fluid_regions']) {
    const task = tasks.find((candidate) => candidate.python_name === name)
    if (!task?.child_template) continue
    const childName = defaultChildName(task, 1)
    result[taskPathKey([name])] = [{ id: childName, name: childName, optional: true }]
  }
  return result
}

interface EditorStateProps {
  included: MeshingIncludedMap
  values: MeshingValueMap
  showDeveloper: boolean
  lengthUnit: string
  faceLabelCatalog: string[]
  onToggle: (key: string, checked: boolean) => void
  onValueChange: (key: string, value: MeshingPresetValue) => void
}

function LabelSelectionControl({
  argument,
  faceLabelCatalog = [],
  value,
  disabled,
  onChange,
}: {
  argument: MeshingSchemaArgument
  faceLabelCatalog?: string[]
  value: MeshingPresetValue
  disabled: boolean
  onChange: (value: MeshingPresetValue) => void
}) {
  const { t } = useTranslation()
  const [filterText, setFilterText] = useState('')
  const selected = Array.isArray(value) ? value.map(String) : []
  const available = Array.from(
    new Set([...(argument.allowed_values ?? []).map(String), ...faceLabelCatalog, ...selected]),
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
        mode="multiple"
        value={selected}
        disabled={disabled}
        aria-label={localizedAnsysTerm(argument.display_name || argument.name, argument.name)}
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
  faceLabelCatalog = [],
  allowedValuesOverride,
  value,
  disabled,
  onChange,
}: {
  argument: MeshingSchemaArgument
  faceLabelCatalog?: string[]
  allowedValuesOverride?: MeshingPresetValue[] | null
  value: MeshingPresetValue
  disabled: boolean
  onChange: (value: MeshingPresetValue) => void
}) {
  const allowedValues = allowedValuesOverride ?? argument.allowed_values
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
        faceLabelCatalog={faceLabelCatalog}
        value={value}
        disabled={disabled}
        onChange={onChange}
      />
    )
  }

  if (argument.value_type === 'bool') {
    return <Switch checked={Boolean(value)} disabled={disabled} onChange={onChange} />
  }

  if (allowedValues?.length) {
    const options = allowedValues.map((item) => ({
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
              next.map((entry) => allowedValues.find((item) => String(item) === entry) ?? entry),
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
        aria-label={localizedAnsysTerm(argument.display_name || argument.name, argument.name)}
        options={options}
        onChange={(next) => onChange(allowedValues.find((item) => String(item) === next) ?? next)}
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
  faceLabelCatalog,
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
    (leaf) =>
      (showDeveloper || !isDeveloperArgument(leaf.argument)) &&
      isArgumentConditionVisible(
        leaf.argument,
        task,
        taskPath,
        childInstanceId,
        values,
        leaf.argumentPath,
        leaf.parentConditions,
      ) &&
      !(
        taskPath[0] === 'import_geometry' &&
        ['file_name', 'file_names', 'mesh_file_name'].includes(leaf.argument.name)
      ),
  )
  const primaryLeaves = visibleLeaves.filter(
    (leaf) =>
      !isDeveloperArgument(leaf.argument) &&
      ((task.python_name === 'add_local_sizing' &&
        LOCAL_SIZING_MAIN_CONTROLS.has(leaf.argument.name)) ||
        !isAdvancedArgument(leaf.argument)),
  )
  const advancedLeaves = visibleLeaves.filter(
    (leaf) =>
      !isDeveloperArgument(leaf.argument) &&
      isAdvancedArgument(leaf.argument) &&
      !(
        task.python_name === 'add_local_sizing' &&
        LOCAL_SIZING_MAIN_CONTROLS.has(leaf.argument.name)
      ),
  )
  const developerLeaves = showDeveloper
    ? visibleLeaves.filter((leaf) => isDeveloperArgument(leaf.argument))
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
        <div className="meshing-argument-label">
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
        </div>
        <div className="meshing-argument-control">
          <ArgumentControl
            argument={leaf.argument}
            faceLabelCatalog={faceLabelCatalog}
            value={current}
            disabled={!editable}
            onChange={(value) => onValueChange(key, value)}
          />
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

interface BoundaryMappingRow {
  id: string
  name: string
  type: string
}

function BoundaryMappingsEditor({
  task,
  values,
  onToggle,
  onValueChange,
  faceLabelCatalog,
}: Pick<EditorStateProps, 'values' | 'onToggle' | 'onValueChange' | 'faceLabelCatalog'> & {
  task: MeshingSchemaTask
}) {
  const taskPath = [task.python_name]
  const selectionTypeKey = selectionKey(taskPath, null, ['selection_type'])
  const selectionType = String(values[selectionTypeKey] ?? 'zone')
  const labelMode = selectionType === 'label'
  const nameKey = selectionKey(taskPath, null, [
    labelMode ? 'boundary_label_list' : 'boundary_zone_list',
  ])
  const typeKey = selectionKey(taskPath, null, [
    labelMode ? 'boundary_label_type_list' : 'boundary_zone_type_list',
  ])
  const names = Array.isArray(values[nameKey]) ? values[nameKey].map(String) : []
  const types = Array.isArray(values[typeKey]) ? values[typeKey].map(String) : []
  const allowedArgument = task.arguments.find(
    (argument) => argument.name === 'boundary_allowed_type_list',
  )
  const allowedTypes = allowedArgument
    ? (defaultArgumentValue(allowedArgument) as string[])
    : ['wall', 'velocity-inlet', 'pressure-outlet', 'symmetry', 'internal']
  const rows: BoundaryMappingRow[] = names.map((name, index) => ({
    id: `${index}:${name}`,
    name,
    type: types[index] ?? 'wall',
  }))
  const [draftNames, setDraftNames] = useState<Record<string, string>>({})
  const [newZoneName, setNewZoneName] = useState('')
  const [newZoneType, setNewZoneType] = useState('wall')

  const commit = (next: BoundaryMappingRow[]): void => {
    onValueChange(selectionTypeKey, selectionType)
    onToggle(selectionTypeKey, true)
    onValueChange(
      nameKey,
      next.map((row) => row.name),
    )
    onValueChange(
      typeKey,
      next.map((row) => row.type),
    )
    onToggle(nameKey, next.length > 0)
    onToggle(typeKey, next.length > 0)
  }

  const addBoundary = (): void => {
    const name = newZoneName.trim()
    if (!name) return
    commit([...rows, { id: `${rows.length}:${name}`, name, type: newZoneType }])
    setNewZoneName('')
  }

  return (
    <Space direction="vertical" size={12} className="full-width">
      <Typography.Text type="secondary">
        选择按几何区域或共享面标签设置边界，并为每项指定边界类型。
      </Typography.Text>
      <Space wrap>
        <Typography.Text strong>选择方式</Typography.Text>
        <Select
          aria-label="更新边界选择方式"
          value={selectionType}
          options={[
            { value: 'zone', label: '几何区域' },
            { value: 'label', label: '共享面标签' },
          ]}
          onChange={(next) => {
            onValueChange(selectionTypeKey, next)
            onToggle(selectionTypeKey, true)
            setNewZoneName('')
          }}
          style={{ minWidth: 180 }}
        />
      </Space>
      {labelMode && faceLabelCatalog.length === 0 ? (
        <Typography.Text type="secondary">
          共享面标签目录为空。请先从参考模型读取标签，或在页面上方添加标签。
        </Typography.Text>
      ) : null}
      <Table<BoundaryMappingRow>
        size="small"
        rowKey="id"
        pagination={false}
        tableLayout="auto"
        dataSource={rows}
        locale={{ emptyText: '尚未添加边界设置' }}
        columns={[
          {
            title: labelMode ? '共享面标签' : '几何区域名称',
            dataIndex: 'name',
            key: 'name',
            width: '52%',
            render: (_value, row) =>
              labelMode ? (
                <Select
                  value={row.name || undefined}
                  aria-label={`共享面标签 ${row.name || '待选择'}`}
                  options={faceLabelCatalog.map((label) => ({ value: label, label }))}
                  popupMatchSelectWidth={260}
                  className="full-width"
                  onChange={(name) =>
                    commit(rows.map((item) => (item.id === row.id ? { ...item, name } : item)))
                  }
                />
              ) : (
                <Input
                  value={draftNames[row.id] ?? row.name}
                  aria-label={`几何区域名称 ${row.name || '待填写'}`}
                  onChange={(event) =>
                    setDraftNames((current) => ({ ...current, [row.id]: event.target.value }))
                  }
                  onBlur={() => {
                    const name = (draftNames[row.id] ?? row.name).trim()
                    if (!name) return
                    commit(rows.map((item) => (item.id === row.id ? { ...item, name } : item)))
                    setDraftNames((current) => {
                      const next = { ...current }
                      delete next[row.id]
                      return next
                    })
                  }}
                />
              ),
          },
          {
            title: '边界类型',
            dataIndex: 'type',
            key: 'type',
            width: 280,
            render: (_value, row) => (
              <Select
                value={row.type}
                aria-label={`边界类型 ${row.name}`}
                popupMatchSelectWidth={260}
                className="full-width"
                options={allowedTypes.map((type) => ({
                  value: type,
                  label: localizedAnsysValue(type),
                }))}
                onChange={(type) =>
                  commit(rows.map((item) => (item.id === row.id ? { ...item, type } : item)))
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
      <Space.Compact className="full-width">
        {labelMode ? (
          <Select
            value={newZoneName || undefined}
            placeholder="选择共享面标签"
            options={faceLabelCatalog.map((label) => ({ value: label, label }))}
            popupMatchSelectWidth={260}
            className="full-width"
            onChange={setNewZoneName}
          />
        ) : (
          <Input
            value={newZoneName}
            maxLength={200}
            placeholder="输入 Fluent 区域名称"
            onChange={(event) => setNewZoneName(event.target.value)}
            onPressEnter={(event) => {
              event.preventDefault()
              addBoundary()
            }}
          />
        )}
        <Select
          value={newZoneType}
          popupMatchSelectWidth={260}
          options={allowedTypes.map((type) => ({ value: type, label: localizedAnsysValue(type) }))}
          onChange={setNewZoneType}
        />
        <Button icon={<PlusOutlined />} disabled={!newZoneName.trim()} onClick={addBoundary}>
          添加边界
        </Button>
      </Space.Compact>
    </Space>
  )
}

function FaceLabelCatalogEditor({
  labels,
  onAdd,
  onRemove,
}: {
  labels: string[]
  onAdd: (label: string) => void
  onRemove: (label: string) => void
}) {
  const [draft, setDraft] = useState('')
  const add = (): void => {
    const label = draft.trim()
    if (!label) return
    onAdd(label)
    setDraft('')
  }
  return (
    <Card size="small" title="共享面标签目录" className="meshing-face-label-catalog">
      <Space direction="vertical" size={10} className="full-width">
        <Typography.Text type="secondary">
          目录中的标签可供局部尺寸、边界层和更新边界选择。没有参考模型时，可以在这里手动添加。
        </Typography.Text>
        <Space.Compact className="full-width">
          <Input
            value={draft}
            maxLength={200}
            placeholder="输入面标签名称，按回车或点击添加"
            onChange={(event) => setDraft(event.target.value)}
            onPressEnter={(event) => {
              event.preventDefault()
              add()
            }}
          />
          <Button icon={<PlusOutlined />} onClick={add} disabled={!draft.trim()}>
            添加标签
          </Button>
        </Space.Compact>
        {labels.length > 0 ? (
          <Space wrap>
            {labels.map((label) => (
              <Tag key={label} closable onClose={() => onRemove(label)}>
                {label}
              </Tag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">
            还没有标签。可以读取参考模型，或手动添加。
          </Typography.Text>
        )}
      </Space>
    </Card>
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

  if (task.python_name === 'update_boundaries') {
    return (
      <BoundaryMappingsEditor
        task={task}
        values={editorProps.values}
        faceLabelCatalog={editorProps.faceLabelCatalog}
        onToggle={editorProps.onToggle}
        onValueChange={editorProps.onValueChange}
      />
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
            <Collapse
              key={instance.id}
              className="meshing-child-collapse"
              defaultActiveKey={[instance.id]}
              items={[
                {
                  key: instance.id,
                  label: instance.name,
                  extra: (
                    <Button
                      danger
                      type="text"
                      icon={<DeleteOutlined />}
                      aria-label={t('meshing.removeChildInstance')}
                      onClick={(event) => {
                        event.stopPropagation()
                        onRemoveChild(taskPath, instance.id)
                      }}
                    />
                  ),
                  children: (
                    <Space direction="vertical" size={14} className="full-width">
                      <Form.Item
                        label={t('meshing.childInstanceName')}
                        required
                        className="meshing-child-name-field"
                      >
                        <Input
                          value={instance.name}
                          placeholder={t('meshing.childInstanceNamePlaceholder')}
                          onChange={(event) =>
                            onRenameChild(taskPath, instance.id, event.target.value)
                          }
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
                  ),
                },
              ]}
            />
          ))
        : null}
    </Space>
  )
}

export function MeshingAutomationCreatePage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const categoryId = new URLSearchParams(location.search).get('category_id') ?? 'uncategorized'
  const editMatch = useMatch('/meshing/:id/edit')
  const sourceAutomationId = Number(editMatch?.params.id ?? 0)
  const isEditing = sourceAutomationId > 0
  const pageTitle = isEditing ? t('meshing.editTitle') : t('meshing.createTitle')
  const pageDescription = isEditing ? t('meshing.editDescription') : t('meshing.createDescription')
  const [form] = Form.useForm<MeshingFormValues>()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [workflowType, setWorkflowType] = useState<MeshingWorkflowType>('watertight')
  const [sourceAutomation, setSourceAutomation] = useState<MeshingAutomation | null>(null)
  const [categories, setCategories] = useState<PartCategory[]>([])
  const [schema, setSchema] = useState<MeshingWorkflowSchema | null>(null)
  const [workflowContract, setWorkflowContract] = useState<MeshingWorkflowContract | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [referenceLabels, setReferenceLabels] = useState<string[]>([])
  const [faceLabelCatalog, setFaceLabelCatalog] = useState<string[]>([])
  const [readingReference, setReadingReference] = useState(false)
  const [referenceReadError, setReferenceReadError] = useState<string | null>(null)
  const [included, setIncluded] = useState<MeshingIncludedMap>({})
  const [values, setValues] = useState<MeshingValueMap>({})
  const [defaultValues, setDefaultValues] = useState<MeshingValueMap>({})
  const [childInstances, setChildInstances] = useState<MeshingChildInstanceMap>({})
  const [activeStepKey, setActiveStepKey] = useState<string>('import_geometry')
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())
  const [showDeveloper, setShowDeveloper] = useState(false)
  const [loading, setLoading] = useState(true)
  const [reloadRevision, setReloadRevision] = useState(0)
  const [saving, setSaving] = useState(false)
  const [editorRevision, setEditorRevision] = useState(0)
  const [autoSaveState, setAutoSaveState] = useState<'saved' | 'saving' | 'pending' | 'error'>(
    'saved',
  )
  const [autoSaveRetry, setAutoSaveRetry] = useState(0)
  const [hasTemplateEdit, setHasTemplateEdit] = useState(false)
  const autoSavedRevisionRef = useRef(0)
  const autoSaveInFlightRef = useRef(false)
  const latestEditorRevisionRef = useRef(0)
  const initializedEditorKeyRef = useRef<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const templateCategoryId = sourceAutomation?.category_id ?? categoryId
  const templateCategoryName =
    categories.find((category) => category.id === templateCategoryId)?.name ?? ''

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
  }, [isEditing, reloadRevision, sidecarState, sourceAutomationId])

  useEffect(() => {
    if (sidecarState !== 'ready') return
    if (isEditing && sourceAutomation === null) return
    const initializationKey = JSON.stringify([
      isEditing ? (sourceAutomation?.id ?? null) : 'new-template',
      workflowType,
      reloadRevision,
    ])
    if (initializedEditorKeyRef.current === initializationKey) return

    let active = true
    void Promise.all([
      fluentAiService.meshing.schema(workflowType),
      fluentAiService.models.list(),
      fluentAiService.categories.list(),
      workflowType === 'watertight'
        ? fluentAiService.meshing.workflowSchema('watertight')
        : Promise.resolve(null),
    ])
      .then(([nextSchema, nextModels, nextCategories, nextContract]) => {
        if (!active) return
        setSchema(nextSchema)
        setWorkflowContract(nextContract)
        setModels(nextModels)
        setCategories(nextCategories)
        if (isEditing && sourceAutomation) {
          const restored = restoreEditorState(nextSchema.tasks, sourceAutomation.preset.items)
          setChildInstances(restored.childInstances)
          setValues(restored.values)
          const childDefaults = buildInitialValues(nextSchema.tasks, restored.childInstances)
          setDefaultValues(childDefaults)
          setIncluded(restored.included)
          setFaceLabelCatalog(
            Array.from(
              new Set([
                ...(sourceAutomation.preset.face_label_catalog ?? []),
                ...collectFaceLabels(sourceAutomation.preset.items),
              ]),
            ).sort((left, right) => left.localeCompare(right)),
          )
        } else {
          const initialChildren =
            workflowType === 'watertight' ? buildInitialChildInstances(nextSchema.tasks) : {}
          setChildInstances(initialChildren)
          const initialValues = buildInitialValues(nextSchema.tasks, initialChildren)
          setValues(initialValues)
          setDefaultValues(initialValues)
          setIncluded({})
          setFaceLabelCatalog([])
          setHasTemplateEdit(false)
        }
        setCompletedSteps(new Set())
        setActiveStepKey(
          workflowType === 'watertight'
            ? WATERTIGHT_STEP_TASKS[0]
            : (nextSchema.tasks[0]?.python_name ?? ''),
        )
        initializedEditorKeyRef.current = initializationKey
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
  }, [isEditing, reloadRevision, sidecarState, sourceAutomation, workflowType])

  const reload = (): void => {
    setError(null)
    setLoading(true)
    if (isEditing) setSourceAutomation(null)
    setReloadRevision((revision) => revision + 1)
  }

  useEffect(() => {
    if (!isEditing || !sourceAutomation || loading || schema === null) return
    form.setFieldsValue({
      name: sourceAutomation.name,
      description: sourceAutomation.description,
      model_family: templateCategoryName,
      reference_model_id: sourceAutomation.reference_model_id,
    })
  }, [form, isEditing, loading, schema, sourceAutomation, templateCategoryName])

  const importedFileFormat = String(
    values[selectionKey(['import_geometry'], null, ['file_format'])] ?? 'CAD',
  )
  const lengthUnit = String(
    importedFileFormat === 'Mesh'
      ? (values[selectionKey(['import_geometry'], null, ['mesh_unit'])] ?? 'm')
      : (values[selectionKey(['import_geometry'], null, ['length_unit'])] ?? 'm'),
  )

  const readReferenceLabels = async (): Promise<void> => {
    const modelId = form.getFieldValue('reference_model_id') as number | null
    if (!modelId) {
      message.warning('请先选择参考模型。')
      return
    }
    setReadingReference(true)
    try {
      const result = await fluentAiService.meshing.inspectReferenceModel(modelId)
      setReferenceLabels(result.labels)
      setReferenceReadError(null)
      setFaceLabelCatalog((current) =>
        Array.from(new Set([...current, ...result.labels])).sort((left, right) =>
          left.localeCompare(right),
        ),
      )
      setHasTemplateEdit(true)
      markEdited()
      message.success(result.message)
    } catch (inspectionError) {
      const detail =
        inspectionError instanceof Error ? inspectionError.message : String(inspectionError)
      setReferenceReadError(detail)
      message.error(detail)
    } finally {
      setReadingReference(false)
    }
  }

  const workflowSteps = useMemo(() => {
    const tasks = schema?.tasks ?? []
    if (workflowType !== 'watertight') return tasks
    const byName = new Map(tasks.map((task) => [task.python_name, task]))
    const stepOrder = [...(workflowContract?.step_order ?? WATERTIGHT_STEP_TASKS)]
    const geometryTask = byName.get('describe_geometry')
    const geometryTypeArgument = geometryTask?.arguments.find(
      (argument) => argument.name === 'setup_type',
    )
    const geometryType = String(
      values[selectionKey(['describe_geometry'], null, ['setup_type'])] ??
        (geometryTypeArgument ? defaultArgumentValue(geometryTypeArgument) : ''),
    )
    const geometryValue = (name: string): string => {
      const argument = geometryTask?.arguments.find((candidate) => candidate.name === name)
      return String(
        values[selectionKey(['describe_geometry'], null, [name])] ??
          (argument ? defaultArgumentValue(argument) : 'No'),
      )
    }
    return stepOrder
      .filter((name) => {
        const rule = workflowContract?.conditional_tasks?.[name]
        if (!rule) return true
        if (rule.geometry && !rule.geometry.includes(geometryType)) return false
        if (
          rule.argument &&
          String(
            values[selectionKey(['describe_geometry'], null, [rule.argument])] ??
              rule.default ??
              geometryValue(rule.argument),
          ) !== rule.equals
        )
          return false
        return true
      })
      .map((name) => byName.get(name))
      .filter((task): task is MeshingSchemaTask => task !== undefined)
  }, [schema, workflowType, workflowContract, values])

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

  const validateTask = useCallback(
    (task: MeshingSchemaTask): string[] => {
      const result = buildMeshingPresetItems([task], included, values, childInstances)
      const errors = result.issues.map((issue) => {
        if (issue.code === 'childNameRequired') return `${issue.taskName}：请填写子任务名称。`
        if (issue.code === 'duplicateChildName')
          return `${issue.taskName}：子任务名称“${issue.childName}”重复。`
        return `${issue.taskName}：至少选择一个参数。`
      })
      if (task.python_name === 'update_boundaries') {
        const selectionType = String(
          values[selectionKey(['update_boundaries'], null, ['selection_type'])] ?? 'zone',
        )
        const nameArgument =
          selectionType === 'label' ? 'boundary_label_list' : 'boundary_zone_list'
        const typeArgument =
          selectionType === 'label' ? 'boundary_label_type_list' : 'boundary_zone_type_list'
        const names = values[selectionKey(['update_boundaries'], null, [nameArgument])]
        const types = values[selectionKey(['update_boundaries'], null, [typeArgument])]
        const boundaryNames = Array.isArray(names) ? names.map(String) : []
        const boundaryTypes = Array.isArray(types) ? types.map(String) : []
        if (boundaryNames.length !== boundaryTypes.length) {
          errors.push('边界名称和边界类型的数量需要一致。')
        }
        if (boundaryNames.some((name) => !name.trim())) {
          errors.push(
            selectionType === 'label'
              ? '请选择每个边界的面标签。'
              : '请填写每个边界的几何区域名称。',
          )
        }
        if (
          new Set(boundaryNames.map((name) => name.trim().toLowerCase())).size !==
          boundaryNames.length
        ) {
          errors.push(selectionType === 'label' ? '面标签不能重复。' : '几何区域名称不能重复。')
        }
      }
      for (const item of result.items) {
        const argumentsToValidate = item.compound_child_name
          ? (task.child_template?.arguments ?? [])
          : task.arguments
        const argument = flattenArgumentLeaves(argumentsToValidate).find(
          (leaf) => leaf.argumentPath.join('.') === item.argument_path.join('.'),
        )?.argument
        const labelArgument = [
          'boi_face_label_list',
          'bl_label_list',
          'zone_selection_list',
          'boundary_label_list',
        ].includes(item.argument_path.at(-1) ?? '')
        if (!argument || item.value_mode === 'at_use') continue
        if (labelArgument && (!Array.isArray(item.value) || item.value.length === 0)) {
          errors.push(`${argument.display_name || argument.name}：至少选择一个面标签。`)
        }
        if (
          !labelArgument &&
          argument.allowed_values &&
          !(
            task.python_name === 'update_boundaries' &&
            item.argument_path.at(-1) === 'selection_type' &&
            ['label', 'zone'].includes(String(item.value))
          ) &&
          !argument.allowed_values.some(
            (value) => JSON.stringify(value) === JSON.stringify(item.value),
          )
        ) {
          errors.push(`${argument.display_name || argument.name}：请选择 Fluent 提供的有效选项。`)
        }
        if (
          argument.value_type === 'int' &&
          (typeof item.value !== 'number' || !Number.isInteger(item.value))
        ) {
          errors.push(`${argument.display_name || argument.name}：请输入整数。`)
        } else if (
          argument.value_type === 'float' &&
          (typeof item.value !== 'number' || !Number.isFinite(item.value))
        ) {
          errors.push(`${argument.display_name || argument.name}：请输入有效数字。`)
        } else if (
          argument.value_type === 'string' &&
          (typeof item.value !== 'string' || !item.value.trim())
        ) {
          errors.push(`${argument.display_name || argument.name}：此项不能为空。`)
        }
      }
      return [...new Set(errors)]
    },
    [childInstances, included, values],
  )

  const selectStep = (task: MeshingSchemaTask): void => {
    if (activeTask) {
      const issues = validateTask(activeTask)
      if (issues.length > 0) {
        void message.error(`${localizedMeshingTaskName(t, activeTask)}：${issues.join('；')}`)
        setCompletedSteps((current) => {
          const next = new Set(current)
          next.delete(activeTask.python_name)
          return next
        })
      } else {
        setCompletedSteps((current) => new Set(current).add(activeTask.python_name))
      }
    }
    setActiveStepKey(task.python_name)
  }

  const markEdited = (): void => {
    setAutoSaveState('pending')
    setEditorRevision((revision) => {
      const next = revision + 1
      latestEditorRevisionRef.current = next
      return next
    })
  }
  const toggle = (key: string, checked: boolean) => {
    setIncluded((current) => ({ ...current, [key]: checked }))
    setHasTemplateEdit(true)
    markEdited()
  }
  const changeValue = (key: string, value: MeshingPresetValue) => {
    const valueDiffersFromDefault = JSON.stringify(defaultValues[key]) !== JSON.stringify(value)
    setValues((current) => ({ ...current, [key]: value }))
    setIncluded((current) => {
      const next = { ...current }
      if (!valueDiffersFromDefault) delete next[key]
      else next[key] = true
      return next
    })
    try {
      const parsed = JSON.parse(key) as unknown[]
      const childId = typeof parsed[1] === 'string' ? parsed[1] : null
      if (childId) {
        const taskPath = Array.isArray(parsed[0]) ? parsed[0].map(String) : []
        const childHasChangedValue =
          valueDiffersFromDefault ||
          Object.entries(included).some(([candidateKey, isIncluded]) => {
            if (!isIncluded || candidateKey === key) return false
            try {
              const candidate = JSON.parse(candidateKey) as unknown[]
              return (
                candidate[0] &&
                JSON.stringify(candidate[0]) === JSON.stringify(taskPath) &&
                candidate[1] === childId
              )
            } catch {
              return false
            }
          })
        setChildInstances((current) => {
          const pathKey = taskPathKey(taskPath)
          return {
            ...current,
            [pathKey]: (current[pathKey] ?? []).map((instance) =>
              instance.id === childId ? { ...instance, optional: !childHasChangedValue } : instance,
            ),
          }
        })
      }
    } catch {
      // Parameter keys are generated internally; malformed keys do not affect the editor.
    }
    const argumentName = (() => {
      try {
        const parsed = JSON.parse(key) as unknown[]
        const path = parsed[2]
        return Array.isArray(path) ? String(path.at(-1) ?? '') : ''
      } catch {
        return ''
      }
    })()
    if (
      [
        'boi_face_label_list',
        'bl_label_list',
        'zone_selection_list',
        'boundary_label_list',
      ].includes(argumentName) &&
      Array.isArray(value)
    ) {
      const labels = value
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter(Boolean)
      setFaceLabelCatalog((current) =>
        Array.from(new Set([...current, ...labels])).sort((left, right) =>
          left.localeCompare(right),
        ),
      )
    }
    setHasTemplateEdit(true)
    markEdited()
  }

  const addFaceLabel = (label: string): void => {
    if (faceLabelCatalog.includes(label)) {
      message.info(`面标签“${label}”已在目录中。`)
      return
    }
    setFaceLabelCatalog((current) =>
      [...current, label].sort((left, right) => left.localeCompare(right)),
    )
    setHasTemplateEdit(true)
    markEdited()
  }

  const removeFaceLabel = (label: string): void => {
    setFaceLabelCatalog((current) => current.filter((item) => item !== label))
    setValues((current) => {
      const next = { ...current }
      for (const [key, value] of Object.entries(next)) {
        if (!Array.isArray(value)) continue
        let argumentName = ''
        try {
          const parsed = JSON.parse(key) as unknown[]
          const path = parsed[2]
          argumentName = Array.isArray(path) ? String(path.at(-1) ?? '') : ''
        } catch {
          continue
        }
        if (
          ['boi_face_label_list', 'bl_label_list', 'zone_selection_list'].includes(argumentName)
        ) {
          next[key] = value.filter((item) => item !== label)
        }
      }
      return next
    })
    setHasTemplateEdit(true)
    markEdited()
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
    markEdited()
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
    markEdited()
  }

  const renameChild = (taskPath: string[], instanceId: string, name: string) => {
    const key = taskPathKey(taskPath)
    setChildInstances((state) => ({
      ...state,
      [key]: (state[key] ?? []).map((instance) =>
        instance.id === instanceId ? { ...instance, name, optional: false } : instance,
      ),
    }))
    markEdited()
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

  useEffect(() => {
    if (
      (!sourceAutomation && !hasTemplateEdit) ||
      !schema ||
      loading ||
      editorRevision === autoSavedRevisionRef.current
    )
      return
    const timer = window.setTimeout(() => {
      const { items, issues } = buildMeshingPresetItems(
        workflowSteps,
        included,
        values,
        childInstances,
      )
      const formValues = form.getFieldsValue()
      const taskErrors = workflowSteps.flatMap((task) => validateTask(task))
      if (
        issues.length > 0 ||
        taskErrors.length > 0 ||
        (items.length === 0 && faceLabelCatalog.length === 0) ||
        !formValues.name?.trim()
      ) {
        setAutoSaveState('pending')
        return
      }
      if (autoSaveInFlightRef.current) {
        setAutoSaveState('pending')
        return
      }
      const preset: MeshingPresetDocument = {
        schema_version: 2,
        fluent_version: schema.fluent_version,
        workflow_type: workflowType,
        items,
        face_label_catalog: faceLabelCatalog,
      }
      setAutoSaveState('saving')
      autoSaveInFlightRef.current = true
      void (async () => {
        try {
          const validation = await fluentAiService.meshing.validatePreset(preset)
          if (!validation.valid) throw new Error(validation.errors.join('; '))
          const payload = {
            name: formValues.name.trim(),
            description: formValues.description ?? '',
            model_family: templateCategoryName,
            reference_model_id: formValues.reference_model_id ?? null,
            category_id: sourceAutomation?.category_id ?? categoryId,
            preset,
            status: 'draft',
          } as const
          const updated = sourceAutomation
            ? await fluentAiService.meshingAutomations.update(sourceAutomation.id, payload)
            : await fluentAiService.meshingAutomations.create(payload)
          setSourceAutomation(updated)
          autoSavedRevisionRef.current = editorRevision
          setAutoSaveState('saved')
        } catch (autoSaveError) {
          setAutoSaveState('error')
          message.error(
            `自动保存失败：${autoSaveError instanceof Error ? autoSaveError.message : String(autoSaveError)}`,
          )
        } finally {
          autoSaveInFlightRef.current = false
          if (latestEditorRevisionRef.current > autoSavedRevisionRef.current) {
            setAutoSaveRetry((current) => current + 1)
          }
        }
      })()
    }, 700)
    return () => window.clearTimeout(timer)
  }, [
    childInstances,
    defaultValues,
    editorRevision,
    faceLabelCatalog,
    form,
    hasTemplateEdit,
    included,
    loading,
    message,
    schema,
    sourceAutomation,
    autoSaveRetry,
    templateCategoryName,
    categoryId,
    values,
    validateTask,
    workflowType,
    workflowSteps,
  ])

  const save = async (formValues: MeshingFormValues): Promise<void> => {
    if (!schema) return
    const { items, issues } = buildMeshingPresetItems(
      workflowSteps,
      included,
      values,
      childInstances,
    )
    if (issues.length > 0) {
      reportIssues(issues)
      return
    }
    const taskErrors = workflowSteps.flatMap((task) => validateTask(task))
    if (taskErrors.length > 0) {
      message.error([...new Set(taskErrors)].join('；'))
      return
    }
    if (!sourceAutomation && items.length === 0 && faceLabelCatalog.length === 0) {
      message.warning(t('meshing.selectAtLeastOne'))
      return
    }
    const preset: MeshingPresetDocument = {
      schema_version: 2,
      fluent_version: schema.fluent_version,
      workflow_type: workflowType,
      items,
      face_label_catalog: faceLabelCatalog,
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
        model_family: templateCategoryName,
        reference_model_id: formValues.reference_model_id ?? null,
        category_id: sourceAutomation?.category_id ?? categoryId,
        preset,
        status: 'draft',
      } as const
      if (sourceAutomation) {
        const updated = await fluentAiService.meshingAutomations.update(
          sourceAutomation.id,
          payload,
        )
        setSourceAutomation(updated)
        message.success(t('meshing.updated'))
      } else {
        const created = await fluentAiService.meshingAutomations.create(payload)
        setSourceAutomation(created)
        message.success(t('meshing.created'))
      }
      autoSavedRevisionRef.current = editorRevision
      setAutoSaveState('saved')
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
        <div className="meshing-agent-layout">
          <div className="meshing-agent-editor">
            <Card>
              <Form<MeshingFormValues>
                form={form}
                layout="vertical"
                initialValues={{
                  name: '',
                  description: '',
                  model_family: templateCategoryName,
                  reference_model_id: null,
                }}
                onValuesChange={() => markEdited()}
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
                  <Form.Item label={t('meshing.modelFamily')} className="meshing-family-field">
                    <Input
                      aria-label={t('meshing.modelFamily')}
                      value={templateCategoryName}
                      disabled
                    />
                  </Form.Item>
                  {/* The category is fixed by the directory selected in the template library. */}
                  {/* Keep the model family out of the editable form; the backend derives it from category_id. */}
                  <Form.Item
                    name="reference_model_id"
                    label={t('meshing.referenceModel')}
                    className="meshing-model-field"
                  >
                    <Select
                      allowClear
                      onChange={() => {
                        setReferenceLabels([])
                        setReferenceReadError(null)
                      }}
                      options={models.map((model) => ({ value: model.id, label: model.name }))}
                      placeholder={t('meshing.referenceModelPlaceholder')}
                    />
                  </Form.Item>
                </Space>
                <Space wrap>
                  <Button loading={readingReference} onClick={() => void readReferenceLabels()}>
                    从参考模型读取标签
                  </Button>
                  {referenceLabels.length > 0 ? (
                    <Typography.Text type="secondary">
                      已读取 {referenceLabels.length} 个标签：{referenceLabels.join('、')}
                    </Typography.Text>
                  ) : null}
                  <Typography.Text type="secondary">
                    读取参考模型只获取面标签；应用模板时仍需另选目标几何。
                  </Typography.Text>
                </Space>
                {referenceReadError ? (
                  <Alert
                    type="error"
                    showIcon
                    message="读取参考模型面标签失败"
                    description={referenceReadError}
                  />
                ) : null}
                <FaceLabelCatalogEditor
                  labels={faceLabelCatalog}
                  onAdd={addFaceLabel}
                  onRemove={removeFaceLabel}
                />
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
                      faceLabelCatalog={faceLabelCatalog}
                      onToggle={toggle}
                      onValueChange={changeValue}
                      onAddChild={addChild}
                      onRemoveChild={removeChild}
                      onRenameChild={renameChild}
                    />
                    <Typography.Text type="secondary">
                      模板编辑只保存 Fluent 参数，不会在 Fluent 中执行当前步骤。
                    </Typography.Text>
                  </Card>
                ) : null}
                <Form.Item className="form-actions">
                  <Typography.Text type={autoSaveState === 'error' ? 'danger' : 'secondary'}>
                    {autoSaveState === 'saving'
                      ? '正在自动保存…'
                      : autoSaveState === 'saved'
                        ? sourceAutomation
                          ? '参数已自动保存'
                          : '点击保存后，后续修改会自动保存'
                        : autoSaveState === 'error'
                          ? '自动保存失败，请点击保存重试'
                          : sourceAutomation
                            ? '有未保存的修改'
                            : '模板尚未创建'}
                  </Typography.Text>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<SaveOutlined />}
                    loading={saving}
                    aria-label={
                      sourceAutomation ? t('meshing.updateAutomation') : t('meshing.save')
                    }
                  >
                    {saving
                      ? t('pages.automationCreate.saving')
                      : sourceAutomation
                        ? t('meshing.updateAutomation')
                        : t('meshing.save')}
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          </div>
          <TemplateAgentPanel
            templateId={sourceAutomation?.id ?? null}
            activeStep={activeStepKey}
          />
        </div>
      )}
    </PageContent>
  )
}
