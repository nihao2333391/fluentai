import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Alert, App, Button, Card, Collapse, Empty, Input, Space, Tag, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

import type {
  MeshingAutomation,
  MeshingLiveSessionSnapshot,
  MeshingLiveStepReport,
  MeshingPresetItem,
  MeshingPresetValue,
  MeshingReadItemResult,
  MeshingSchemaArgument,
  MeshingSchemaTask,
  MeshingWorkflowSchema,
} from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { localizedAnsysTerm } from '../i18n/ansysLabels'
import { fluentAiService } from '../services/fluentAi'
import { ArgumentControl } from './MeshingAutomationCreatePage'
import { localizedMeshingTaskName } from './meshingLabels'
import { isAdvancedArgument } from './meshingPreset'

const valueKey = (item: {
  task_path: string[]
  argument_path: string[]
  compound_child_name?: string | null
}): string => JSON.stringify([item.task_path, item.argument_path, item.compound_child_name])

const findTaskByPath = (
  tasks: MeshingSchemaTask[],
  taskPath: string[],
  parentPath: string[] = [],
): MeshingSchemaTask | null => {
  for (const task of tasks) {
    const path = [...parentPath, task.python_name]
    if (JSON.stringify(path) === JSON.stringify(taskPath)) return task
    const nested = findTaskByPath(task.children, taskPath, path)
    if (nested) return nested
  }
  return null
}

const findArgument = (
  task: MeshingSchemaTask,
  item: MeshingReadItemResult,
): MeshingSchemaArgument | null => {
  let arguments_ = item.compound_child_name
    ? (task.child_template?.arguments ?? [])
    : task.arguments
  let current: MeshingSchemaArgument | null = null
  for (const part of item.argument_path) {
    current = arguments_.find((argument) => argument.name === part) ?? null
    if (!current) return null
    arguments_ = current.children
  }
  return current
}

const stringifyValue = (value: MeshingPresetValue | null | undefined): string =>
  JSON.stringify(value ?? null)

const statusIcon = (status: string) => {
  if (status === 'completed') return <CheckCircleOutlined />
  if (status === 'failed') return <WarningOutlined />
  if (status === 'running') return <LoadingOutlined />
  if (status === 'active') return <ThunderboltOutlined />
  return <SyncOutlined />
}

type ApplyMode = 'enter' | 'write' | 'poll' | 'execute'

export function MeshingLiveSyncPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const { sessionId = '' } = useParams()
  const [session, setSession] = useState<MeshingLiveSessionSnapshot | null>(null)
  const [automation, setAutomation] = useState<MeshingAutomation | null>(null)
  const [schema, setSchema] = useState<MeshingWorkflowSchema | null>(null)
  const [stepReport, setStepReport] = useState<MeshingLiveStepReport | null>(null)
  const [values, setValues] = useState<Record<string, MeshingPresetValue>>({})
  const [externalKeys, setExternalKeys] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newChildName, setNewChildName] = useState('')
  const lastValuesRef = useRef<Record<string, string>>({})
  const pendingKeysRef = useRef<Set<string>>(new Set())
  const dirtyItemsRef = useRef<Map<string, MeshingPresetItem>>(new Map())
  const writeTimersRef = useRef<Map<string, number>>(new Map())
  const sessionRef = useRef<MeshingLiveSessionSnapshot | null>(null)
  const enteredStepRef = useRef(-1)

  useEffect(() => {
    sessionRef.current = session
  }, [session])

  const applyReport = useCallback((report: MeshingLiveStepReport, mode: ApplyMode) => {
    setSession(report.snapshot)
    setStepReport(report)
    if (!report.read_report) return
    const nextValues: Record<string, MeshingPresetValue> = {}
    const changed = new Set<string>()
    for (const item of report.read_report.items) {
      const key = valueKey(item)
      const value = item.value ?? null
      nextValues[key] = value
      const previous = lastValuesRef.current[key]
      if (
        mode === 'poll' &&
        previous !== undefined &&
        previous !== stringifyValue(value) &&
        !pendingKeysRef.current.has(key)
      ) {
        changed.add(key)
      }
      lastValuesRef.current[key] = stringifyValue(value)
    }
    setValues((current) => {
      if (mode !== 'poll') return nextValues
      const merged = { ...nextValues }
      for (const key of pendingKeysRef.current) {
        if (key in current) merged[key] = current[key]
      }
      return merged
    })
    if (changed.size > 0) {
      setExternalKeys((current) => new Set([...current, ...changed]))
    }
    if (mode !== 'poll') setExternalKeys(new Set())
  }, [])

  const enterStep = useCallback(
    async (stepIndex: number) => {
      if (!sessionId) return
      setBusy(true)
      setError(null)
      try {
        const report = await fluentAiService.meshingLive.enterStep(sessionId, {
          step_index: stepIndex,
        })
        enteredStepRef.current = stepIndex
        applyReport(report, 'enter')
        if (report.status === 'failed') {
          setError(report.message || t('meshing.liveStepFailed'))
        }
      } catch (stepError) {
        setError(stepError instanceof Error ? stepError.message : String(stepError))
      } finally {
        setBusy(false)
      }
    },
    [applyReport, sessionId, t],
  )

  useEffect(() => {
    if (!sessionId) return
    let active = true
    void (async () => {
      try {
        const snapshot = await fluentAiService.meshingLive.get(sessionId)
        const [nextAutomation, nextSchema] = await Promise.all([
          fluentAiService.meshingAutomations.get(snapshot.automation_id),
          fluentAiService.meshing.schema(snapshot.workflow_type),
        ])
        if (!active) return
        setSession(snapshot)
        setAutomation(nextAutomation)
        setSchema(nextSchema)
        setLoading(false)
        if (snapshot.connection?.connected && snapshot.status !== 'failed') {
          await enterStep(snapshot.current_step_index)
        }
      } catch (loadError) {
        if (!active) return
        setError(loadError instanceof Error ? loadError.message : String(loadError))
        setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [enterStep, sessionId])

  useEffect(() => {
    if (!sessionId) return
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const snapshot = await fluentAiService.meshingLive.get(sessionId)
          setSession(snapshot)
          if (snapshot.status === 'starting' || snapshot.status === 'running') return
          if (busy) return
          if (
            snapshot.status === 'waiting' &&
            snapshot.connection?.connected &&
            snapshot.current_step_index !== enteredStepRef.current
          ) {
            await enterStep(snapshot.current_step_index)
            return
          }
          if (!snapshot.connection?.connected) return
          const report = await fluentAiService.meshingLive.readStep(
            sessionId,
            snapshot.current_step_index,
          )
          applyReport(report, 'poll')
        } catch {
          // Poll errors are surfaced by the next explicit action; avoid noisy toasts.
        }
      })()
    }, 2000)
    return () => window.clearInterval(timer)
  }, [applyReport, busy, enterStep, sessionId])

  const currentModel = session?.models[session.current_model_index] ?? null
  const currentTask = useMemo(
    () =>
      schema && session
        ? findTaskByPath(schema.tasks, session.steps[session.current_step_index]?.task_path ?? [])
        : null,
    [schema, session],
  )

  const writeItems = useCallback(
    async (items: MeshingPresetItem[], mode: ApplyMode = 'write') => {
      if (!sessionId || items.length === 0) return null
      try {
        const report = await fluentAiService.meshingLive.writeStep(sessionId, {
          step_index: sessionRef.current?.current_step_index ?? 0,
          items,
        })
        applyReport(report, mode)
        if (report.status === 'failed')
          message.error(report.message || t('meshing.liveWriteFailed'))
        return report
      } catch (writeError) {
        message.error(writeError instanceof Error ? writeError.message : String(writeError))
        return null
      }
    },
    [applyReport, message, sessionId, t],
  )

  const commitPendingItem = useCallback(
    async (key: string) => {
      const item = dirtyItemsRef.current.get(key)
      if (!item) return
      dirtyItemsRef.current.delete(key)
      await writeItems([item])
      pendingKeysRef.current.delete(key)
    },
    [writeItems],
  )

  const updateValue = (
    item: MeshingReadItemResult,
    task: MeshingSchemaTask,
    nextValue: MeshingPresetValue,
  ): void => {
    const key = valueKey(item)
    setValues((current) => ({ ...current, [key]: nextValue }))
    pendingKeysRef.current.add(key)
    dirtyItemsRef.current.set(key, {
      task_path: task ? [...item.task_path] : item.task_path,
      argument_path: [...item.argument_path],
      value: nextValue,
      required: true,
      compound_child_name: item.compound_child_name ?? null,
    })
    const existing = writeTimersRef.current.get(key)
    if (existing) window.clearTimeout(existing)
    writeTimersRef.current.set(
      key,
      window.setTimeout(() => {
        writeTimersRef.current.delete(key)
        void commitPendingItem(key)
      }, 650),
    )
  }

  const flushPending = async (): Promise<void> => {
    if (!sessionId) return
    const pendingItems = [...dirtyItemsRef.current.values()]
    dirtyItemsRef.current.clear()
    for (const timer of writeTimersRef.current.values()) window.clearTimeout(timer)
    writeTimersRef.current.clear()
    if (pendingItems.length > 0) await writeItems(pendingItems)
    pendingKeysRef.current.clear()
  }

  const executeCurrentStep = async (): Promise<void> => {
    if (!session || !sessionId) return
    setBusy(true)
    try {
      await flushPending()
      const report = await fluentAiService.meshingLive.executeStep(sessionId, {
        step_index: session.current_step_index,
      })
      applyReport(report, 'execute')
      if (report.status === 'failed') {
        message.error(report.message || t('meshing.liveStepFailed'))
      } else {
        message.success(t('meshing.liveStepCompleted'))
        if (report.snapshot.current_step_index !== session.current_step_index) {
          await enterStep(report.snapshot.current_step_index)
        }
      }
    } catch (executeError) {
      message.error(executeError instanceof Error ? executeError.message : String(executeError))
    } finally {
      setBusy(false)
    }
  }

  const overrideExternal = async (): Promise<void> => {
    if (!session) return
    await enterStep(session.current_step_index)
    setExternalKeys(new Set())
  }

  const addChild = async (): Promise<void> => {
    if (!currentTask?.child_template || !session) return
    const nameArgument = currentTask.child_template.arguments.find(
      (argument) => argument.name.endsWith('_control_name') || argument.name.endsWith('_name'),
    )
    if (!nameArgument) return
    const defaultStem =
      currentTask.python_name === 'add_boundary_layer' ? 'smooth-transition' : 'facesize'
    const existingNames = new Set(
      (stepReport?.read_report?.items ?? [])
        .map((item) => item.compound_child_name)
        .filter((name): name is string => Boolean(name)),
    )
    const requestedName = newChildName.trim()
    let index = existingNames.size + 1
    let name = requestedName || `${defaultStem}_${index}`
    while (existingNames.has(name)) {
      index += 1
      name = requestedName ? `${requestedName}_${index}` : `${defaultStem}_${index}`
    }
    await flushPending()
    await writeItems([
      {
        task_path: currentTask ? [currentTask.python_name] : [],
        argument_path: ['add_child'],
        value: 'yes',
        required: true,
        compound_child_name: null,
      },
      {
        task_path: [currentTask.python_name],
        argument_path: [nameArgument.name],
        value: name,
        required: true,
        compound_child_name: name,
      },
    ])
    setNewChildName('')
  }

  const nextModel = async (): Promise<void> => {
    if (!sessionId) return
    setBusy(true)
    try {
      const snapshot = await fluentAiService.meshingLive.nextModel(sessionId)
      setSession(snapshot)
      enteredStepRef.current = -1
      if (snapshot.connection?.connected) await enterStep(snapshot.current_step_index)
    } finally {
      setBusy(false)
    }
  }

  const retryModel = async (): Promise<void> => {
    if (!sessionId) return
    setBusy(true)
    try {
      const snapshot = await fluentAiService.meshingLive.retryModel(sessionId)
      setSession(snapshot)
      enteredStepRef.current = -1
      if (snapshot.connection?.connected) await enterStep(snapshot.current_step_index)
    } finally {
      setBusy(false)
    }
  }

  const stopSession = (): void => {
    if (!sessionId) return
    modal.confirm({
      title: t('meshing.liveStopConfirm'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await fluentAiService.meshingLive.stop(sessionId)
        navigate('/meshing')
      },
    })
  }

  if (loading) return <LoadingState />
  if (error && !session) {
    return (
      <PageContent title={t('meshing.liveTitle')} description={t('meshing.liveDescription')}>
        <ErrorState
          title={t('meshing.liveSessionError')}
          description={error}
          retryLabel={t('common.reload')}
        />
      </PageContent>
    )
  }
  if (!session) return null

  const currentStep = session.steps[session.current_step_index]
  const readItems = stepReport?.read_report?.items ?? []
  const groupedItems = new Map<string, MeshingReadItemResult[]>()
  for (const item of readItems) {
    const group = item.compound_child_name ?? ''
    groupedItems.set(group, [...(groupedItems.get(group) ?? []), item])
  }
  const renderParameter = (item: MeshingReadItemResult) => {
    if (!currentTask) return null
    const argument = findArgument(currentTask, item)
    if (!argument) return null
    const key = valueKey(item)
    const external = externalKeys.has(key)
    return (
      <div key={key} className={`live-parameter-row ${external ? 'is-external' : ''}`}>
        <Space direction="vertical" size={2} className="live-parameter-label">
          <Typography.Text strong>
            {localizedAnsysTerm(argument.display_name || argument.name)}
          </Typography.Text>
          <Typography.Text type="secondary" className="live-parameter-path">
            {item.argument_path.join(' > ')}
          </Typography.Text>
          {external ? <Tag color="warning">{t('meshing.externalModified')}</Tag> : null}
        </Space>
        <div className="live-parameter-control">
          <ArgumentControl
            argument={argument}
            value={values[key] ?? null}
            disabled={busy || session.status === 'running' || session.status === 'stopped'}
            onChange={(value) => updateValue(item, currentTask, value)}
          />
        </div>
      </div>
    )
  }

  return (
    <PageContent
      title={automation?.name ?? session.automation_name}
      description={t('meshing.liveDescription')}
      actions={
        <Space wrap>
          <Tag
            color={
              session.status === 'starting'
                ? 'gold'
                : session.connection?.connected
                  ? 'green'
                  : 'red'
            }
          >
            {session.status === 'starting'
              ? t('meshing.liveStarting')
              : session.connection?.connected
                ? t('meshing.liveConnected')
                : t('meshing.liveDisconnected')}
          </Tag>
          <Tag color="blue">
            {t('meshing.liveModelProgress', {
              current: session.current_model_index + 1,
              total: session.models.length,
              name: currentModel?.name ?? '',
            })}
          </Tag>
          <Button danger icon={<StopOutlined />} onClick={stopSession}>
            {t('meshing.liveStop')}
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={16} className="full-width">
        {error ? (
          <Alert
            type="error"
            showIcon
            message={t('meshing.liveSessionError')}
            description={error}
          />
        ) : null}
        {session.message ? (
          <Alert
            type={session.status === 'failed' ? 'error' : 'info'}
            showIcon
            message={session.message}
          />
        ) : null}
        {externalKeys.size > 0 ? (
          <Alert
            type="warning"
            showIcon
            message={t('meshing.externalConflictTitle')}
            description={t('meshing.externalConflictDescription')}
            action={
              <Button size="small" onClick={() => void overrideExternal()}>
                {t('meshing.overwriteExternal')}
              </Button>
            }
          />
        ) : null}

        <Card size="small" title={t('meshing.liveModelQueue')}>
          <Space wrap>
            {session.models.map((model, index) => (
              <Tag
                key={model.model_id}
                color={
                  model.status === 'failed'
                    ? 'red'
                    : model.status === 'completed'
                      ? 'green'
                      : index === session.current_model_index
                        ? 'blue'
                        : 'default'
                }
              >
                {index + 1}. {model.name} · {t(`meshing.liveModelStatuses.${model.status}`)}
              </Tag>
            ))}
          </Space>
          {currentModel?.error ? (
            <Typography.Paragraph type="danger" className="meshing-live-error">
              {currentModel.error}
            </Typography.Paragraph>
          ) : null}
          <Space className="meshing-live-model-actions">
            {currentModel?.status === 'failed' ? (
              <Button icon={<ReloadOutlined />} onClick={() => void retryModel()} loading={busy}>
                {t('meshing.retryModel')}
              </Button>
            ) : null}
            {session.current_model_index < session.models.length - 1 &&
            currentModel?.status !== 'pending' ? (
              <Button icon={<ArrowRightOutlined />} onClick={() => void nextModel()} loading={busy}>
                {t('meshing.nextModel')}
              </Button>
            ) : null}
          </Space>
        </Card>

        <div className="meshing-stepper-scroll">
          <div className="meshing-stepper live-meshing-stepper">
            {session.steps.map((step, index) => {
              const task = schema ? findTaskByPath(schema.tasks, step.task_path) : null
              return (
                <button
                  key={step.task_path.join('/')}
                  type="button"
                  className={`meshing-step ${index === session.current_step_index ? 'is-active' : ''} ${step.status === 'completed' ? 'is-complete' : ''} live-step-${step.status}`}
                  onClick={() => void enterStep(index)}
                  disabled={
                    busy ||
                    session.status === 'starting' ||
                    session.status === 'running' ||
                    session.status === 'stopped'
                  }
                  aria-current={index === session.current_step_index ? 'step' : undefined}
                >
                  <span className="meshing-step-icon">{statusIcon(step.status)}</span>
                  <span className="meshing-step-copy">
                    <strong>{task ? localizedMeshingTaskName(t, task) : step.task_path[0]}</strong>
                    <small>{t(`meshing.liveStepStatuses.${step.status}`)}</small>
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {currentTask && currentStep ? (
          <Card
            className="meshing-step-panel live-step-panel"
            title={
              <Space>
                <span>{localizedMeshingTaskName(t, currentTask)}</span>
                <Tag color={currentStep.status === 'failed' ? 'red' : 'blue'}>
                  {t(`meshing.liveStepStatuses.${currentStep.status}`)}
                </Tag>
              </Space>
            }
          >
            <Space direction="vertical" size={14} className="full-width">
              {currentTask.child_template ? (
                <Space wrap className="meshing-live-add-child">
                  <Input
                    value={newChildName}
                    placeholder={t('meshing.liveChildNamePlaceholder')}
                    onChange={(event) => setNewChildName(event.target.value)}
                    className="meshing-live-child-input"
                  />
                  <Button icon={<PlusOutlined />} onClick={() => void addChild()} loading={busy}>
                    {t('meshing.liveAddChild')}
                  </Button>
                </Space>
              ) : null}

              {[...groupedItems.entries()].map(([childName, items]) => {
                const primary = items.filter((item) => {
                  const argument = findArgument(currentTask, item)
                  return argument ? !isAdvancedArgument(argument) : true
                })
                const advanced = items.filter((item) => {
                  const argument = findArgument(currentTask, item)
                  return argument ? isAdvancedArgument(argument) : false
                })
                return (
                  <Card
                    key={childName || 'task'}
                    size="small"
                    title={childName ? `${t('meshing.liveChildGroup')}: ${childName}` : undefined}
                  >
                    <Space direction="vertical" size={10} className="full-width">
                      {primary.map(renderParameter)}
                      {advanced.length > 0 ? (
                        <Collapse
                          items={[
                            {
                              key: 'advanced',
                              label: `${t('meshing.advancedOptions')} (${advanced.length})`,
                              children: (
                                <Space direction="vertical" size={10} className="full-width">
                                  {advanced.map(renderParameter)}
                                </Space>
                              ),
                            },
                          ]}
                        />
                      ) : null}
                    </Space>
                  </Card>
                )
              })}
              {readItems.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('meshing.liveNoValues')}
                />
              ) : null}
            </Space>
            <Space wrap className="meshing-step-actions">
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={busy}
                disabled={
                  session.status === 'starting' ||
                  session.status === 'running' ||
                  session.status === 'stopped'
                }
                onClick={() => void executeCurrentStep()}
              >
                {t('meshing.liveExecuteStep', {
                  step: localizedMeshingTaskName(t, currentTask),
                })}
              </Button>
              <Button icon={<SyncOutlined />} onClick={() => void overrideExternal()}>
                {t('meshing.liveRewritePreset')}
              </Button>
            </Space>
          </Card>
        ) : null}

        <Collapse
          items={[
            {
              key: 'logs',
              label: t('meshing.liveLogs', { count: session.logs.length }),
              children:
                session.logs.length === 0 ? (
                  <Typography.Text type="secondary">{t('meshing.liveNoLogs')}</Typography.Text>
                ) : (
                  <div className="meshing-live-logs">
                    {session.logs.map((entry) => (
                      <div key={entry.sequence} className={`meshing-live-log is-${entry.level}`}>
                        <Typography.Text type="secondary">
                          {new Date(entry.timestamp).toLocaleTimeString()}
                        </Typography.Text>
                        <Tag
                          color={
                            entry.level === 'error'
                              ? 'red'
                              : entry.level === 'success'
                                ? 'green'
                                : entry.level === 'warning'
                                  ? 'gold'
                                  : 'blue'
                          }
                        >
                          {entry.level}
                        </Tag>
                        <span>{entry.message}</span>
                      </div>
                    ))}
                  </div>
                ),
            },
          ]}
        />
      </Space>
    </PageContent>
  )
}
