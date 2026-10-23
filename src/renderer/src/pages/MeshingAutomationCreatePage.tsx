import { DeleteOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
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
  Segmented,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type {
  MeshingPresetDocument,
  MeshingPresetValue,
  MeshingSchemaArgument,
  MeshingSchemaTask,
  MeshingWorkflowSchema,
  MeshingWorkflowType,
  Model,
} from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
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

interface EditorStateProps {
  included: MeshingIncludedMap
  values: MeshingValueMap
  showDeveloper: boolean
  onToggle: (key: string, checked: boolean) => void
  onValueChange: (key: string, value: MeshingPresetValue) => void
}

let childInstanceCounter = 0

const nextChildInstanceId = (task: MeshingSchemaTask): string => {
  childInstanceCounter += 1
  return `${task.python_name}-${childInstanceCounter}`
}

function ArgumentControl({
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
  if (argument.value_type === 'bool') {
    return <Switch checked={Boolean(value)} disabled={disabled} onChange={onChange} />
  }

  if (argument.allowed_values?.length) {
    const options = argument.allowed_values.map((item) => ({
      value: String(item),
      label: String(item),
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
  onToggle,
  onValueChange,
}: EditorStateProps & {
  task: MeshingSchemaTask
  taskPath: string[]
  childInstanceId: string | null
}) {
  const { t } = useTranslation()
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
    const displayPath = leaf.displayPath.join(' > ')
    return (
      <div key={key} className={`meshing-argument-row ${included[key] ? 'is-included' : ''}`}>
        <Checkbox
          checked={Boolean(included[key])}
          disabled={!editable}
          onChange={(event) => onToggle(key, event.target.checked)}
        >
          <Space direction="vertical" size={2}>
            <Typography.Text strong>{displayPath}</Typography.Text>
            <Typography.Text type="secondary" className="meshing-argument-path">
              {displayPath === technicalPath ? leaf.argument.edit_path : technicalPath}
              {leaf.argument.display_condition
                ? ` · ${t('meshing.conditionLabel')}：${leaf.argument.display_condition}`
                : ''}
            </Typography.Text>
          </Space>
        </Checkbox>
        <div className="meshing-argument-control">
          <ArgumentControl
            argument={leaf.argument}
            value={current}
            disabled={!editable || !included[key]}
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

function CompoundChildEditor({
  task,
  taskPath,
  instances,
  onAdd,
  onRemove,
  onRename,
  ...editorProps
}: EditorStateProps & {
  task: MeshingSchemaTask
  taskPath: string[]
  instances: MeshingChildInstance[]
  onAdd: () => void
  onRemove: (instanceId: string) => void
  onRename: (instanceId: string, name: string) => void
}) {
  const { t } = useTranslation()
  const managedNameArgument = childNameArgument(task)

  return (
    <Space direction="vertical" size={14} className="full-width">
      {task.child_template_warning ? (
        <Alert type="warning" showIcon message={t('meshing.childTemplateFallback')} />
      ) : null}
      <Space wrap>
        <Button type="dashed" icon={<PlusOutlined />} onClick={onAdd}>
          {t('meshing.addChildInstance')}
        </Button>
        <Typography.Text type="secondary">{t('meshing.childInstanceHint')}</Typography.Text>
      </Space>
      {instances.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('meshing.noChildInstances')} />
      ) : (
        instances.map((instance, index) => (
          <Card
            key={instance.id}
            size="small"
            title={`${t('meshing.compoundChild')} ${index + 1}`}
            extra={
              <Button
                danger
                type="text"
                icon={<DeleteOutlined />}
                aria-label={t('meshing.removeChildInstance')}
                onClick={() => onRemove(instance.id)}
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
                  onChange={(event) => onRename(instance.id, event.target.value)}
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
      )}
    </Space>
  )
}

function TaskPanel({
  task,
  taskPath,
  childInstances,
  onAddChild,
  onRemoveChild,
  onRenameChild,
  ...editorProps
}: EditorStateProps & {
  task: MeshingSchemaTask
  taskPath: string[]
  childInstances: MeshingChildInstanceMap
  onAddChild: (task: MeshingSchemaTask, taskPath: string[]) => void
  onRemoveChild: (taskPath: string[], instanceId: string) => void
  onRenameChild: (taskPath: string[], instanceId: string, name: string) => void
}) {
  const { t } = useTranslation()
  const instancesKey = taskPathKey(taskPath)
  const hasChildTemplate = Boolean(task.supports_child_template && task.child_template)

  return (
    <Space direction="vertical" size={16} className="full-width">
      {hasChildTemplate ? (
        <CompoundChildEditor
          task={task}
          taskPath={taskPath}
          instances={childInstances[instancesKey] ?? []}
          onAdd={() => onAddChild(task, taskPath)}
          onRemove={(instanceId) => onRemoveChild(taskPath, instanceId)}
          onRename={(instanceId, name) => onRenameChild(taskPath, instanceId, name)}
          {...editorProps}
        />
      ) : (
        <>
          {task.task_type === 'Compound' && task.child_template_error ? (
            <Alert type="warning" showIcon message={task.child_template_error} />
          ) : null}
          <ArgumentSections
            task={task}
            taskPath={taskPath}
            childInstanceId={null}
            {...editorProps}
          />
        </>
      )}
      {task.children.length > 0 ? (
        <Space direction="vertical" size={12} className="full-width">
          {task.children.map((child) => (
            <Card
              key={taskPathKey([...taskPath, child.python_name])}
              size="small"
              title={localizedMeshingTaskName(t, child)}
            >
              <TaskPanel
                task={child}
                taskPath={[...taskPath, child.python_name]}
                childInstances={childInstances}
                onAddChild={onAddChild}
                onRemoveChild={onRemoveChild}
                onRenameChild={onRenameChild}
                {...editorProps}
              />
            </Card>
          ))}
        </Space>
      ) : null}
    </Space>
  )
}

export function MeshingAutomationCreatePage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<MeshingFormValues>()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [workflowType, setWorkflowType] = useState<MeshingWorkflowType>('watertight')
  const [reloadVersion, setReloadVersion] = useState(0)
  const [schema, setSchema] = useState<MeshingWorkflowSchema | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [included, setIncluded] = useState<MeshingIncludedMap>({})
  const [values, setValues] = useState<MeshingValueMap>({})
  const [childInstances, setChildInstances] = useState<MeshingChildInstanceMap>({})
  const [showDeveloper, setShowDeveloper] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (sidecarState !== 'ready') return
    let active = true
    void Promise.all([fluentAiService.meshing.schema(workflowType), fluentAiService.models.list()])
      .then(([nextSchema, nextModels]) => {
        if (!active) return
        setSchema(nextSchema)
        setModels(nextModels)
        const nextValues: MeshingValueMap = {}
        for (const entry of collectTaskLeaves(nextSchema.tasks)) {
          nextValues[selectionKey(entry.taskPath, null, entry.argumentPath)] = defaultArgumentValue(
            entry.argument,
          )
        }
        setValues(nextValues)
        setIncluded({})
        setChildInstances({})
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
  }, [sidecarState, workflowType, reloadVersion])

  const selectedCount = useMemo(() => Object.values(included).filter(Boolean).length, [included])

  const toggle = (key: string, checked: boolean) =>
    setIncluded((current) => ({ ...current, [key]: checked }))
  const changeValue = (key: string, value: MeshingPresetValue) =>
    setValues((current) => ({ ...current, [key]: value }))

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
      await fluentAiService.meshingAutomations.create({
        name: formValues.name,
        description: formValues.description ?? '',
        model_family: formValues.model_family ?? '',
        reference_model_id: formValues.reference_model_id ?? null,
        preset,
        status: 'draft',
      })
      message.success(t('meshing.created'))
      navigate('/meshing')
    } catch (saveError) {
      message.error(saveError instanceof Error ? saveError.message : String(saveError))
    } finally {
      setSaving(false)
    }
  }

  const tabItems = (schema?.tasks ?? []).map((task) => ({
    key: task.python_name,
    label: (
      <Space direction="vertical" size={0}>
        <span>{localizedMeshingTaskName(t, task)}</span>
        <Typography.Text type="secondary" className="task-type-label">
          {localizedMeshingTaskType(t, task.task_type)}
        </Typography.Text>
      </Space>
    ),
    children: (
      <TaskPanel
        task={task}
        taskPath={[task.python_name]}
        childInstances={childInstances}
        included={included}
        values={values}
        showDeveloper={showDeveloper}
        onToggle={toggle}
        onValueChange={changeValue}
        onAddChild={addChild}
        onRemoveChild={removeChild}
        onRenameChild={renameChild}
      />
    ),
  }))

  if (sidecarState === 'error') {
    return (
      <PageContent title={t('meshing.createTitle')} description={t('meshing.createDescription')}>
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
      title={t('meshing.createTitle')}
      description={t('meshing.createDescription')}
      actions={
        <Space wrap>
          <Tag color="blue">{t('meshing.selectedOptions', { count: selectedCount })}</Tag>
          <Segmented
            value={workflowType}
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
            <Tabs tabPosition="left" items={tabItems} className="meshing-workflow-tabs" />
            <Form.Item className="form-actions">
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>
                {saving ? t('pages.automationCreate.saving') : t('meshing.save')}
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
