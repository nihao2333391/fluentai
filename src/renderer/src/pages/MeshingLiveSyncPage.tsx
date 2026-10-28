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
  MeshingArchiveRecord,
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
  const [manualTakeover, setManualTakeover] = useState(false)
  const [meshPath, setMeshPath] = useState('')
  const [modelingNotes, setModelingNotes] = useState('')
  const [archives, setArchives] = useState<MeshingArchiveRecord[]>([])
  const [archiving, setArchiving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)
  const [newChildName, setNewChildName] = useState('')
  const lastValuesRef = useRef<Record<string, string>>({})
  const pendingKeysRef = useRef<Set<string>>(new Set())
  const dirtyItemsRef = useRef<Map<string, MeshingPresetItem>>(new Map())
  const writeTimersRef = useRef<Map<string, number>>(new Map())
  const sessionRef = useRef<MeshingLiveSessionSnapshot | null>(null)
  const enteredStepRef = useRef(-1)
  const pollInFlightRef = useRef(false)

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
        setArchives(await fluentAiService.meshingLive.archives(sessionId))
        setLoading(false)
      } catch (loadError) {
        if (!active) return
        setError(loadError instanceof Error ? loadError.message : String(loadError))
        setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    let active = true
    const timer = window.setInterval(() => {
      if (pollInFlightRef.current) return
      pollInFlightRef.current = true
      void (async () => {
        try {
          const snapshot = await fluentAiService.meshingLive.get(sessionId)
          if (!active) return
          setSession(snapshot)
          setPollError(null)
          if (
            snapshot.status === 'starting' ||
            snapshot.status === 'running' ||
            snapshot.status === 'failed' ||
            snapshot.status === 'stopped'
          ) {
            return
          }
          if (busy) return
          if (!snapshot.connection?.connected) return
          const report = await fluentAiService.meshingLive.readStep(
            sessionId,
            snapshot.current_step_index,
          )
          if (!active) return
          applyReport(report, 'poll')
          if (report.status === 'failed') {
            setPollError(
              report.read_report?.error ||
                report.message ||
                'Fluent 当前步骤读取失败。平台会自动重试。',
            )
          }
        } catch (pollingError) {
          if (active) {
            setPollError(
              `自动状态刷新失败：${pollingError instanceof Error ? pollingError.message : String(pollingError)}。平台会自动重试。`,
            )
          }
        } finally {
          pollInFlightRef.current = false
        }
      })()
    }, 2000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [applyReport, busy, sessionId])

  const currentModel = session?.models[session.current_model_index] ?? null
  const currentTask = useMemo(
    () =>
      schema && session
        ? findTaskByPath(schema.tasks, session.steps[session.current_step_index]?.task_path ?? [])
        : null,
    [schema, session],
  )
  const phaseLabel = session
    ? session.phase === 'connecting' ? '正在连接 Fluent' :
      session.phase === 'importing' ? '正在导入几何' :
      session.phase === 'preparing_local_sizing' ? '正在写入并回读局部尺寸' :
      session.phase === 'executing_local_sizing' ? '正在 Fluent 中执行局部尺寸' :
      session.phase === 'preparing_surface_mesh' ? '正在写入并回读面网格参数' :
      session.phase === 'surface_ready' ? '面网格设置已就绪，等待检查' :
      session.phase === 'volume_ready' ? '体网格设置已就绪，等待检查' :
      session.phase === 'preparing_surface' ? '正在准备面网格前设置' :
      session.phase === 'preparing_volume' ? '正在准备体网格前设置' :
      session.phase === 'generating_surface' ? '正在生成面网格' :
      session.phase === 'generating_volume' ? '正在生成体网格' :
      session.phase === 'failed' ? '当前阶段准备失败' :
      session.phase === 'completed' ? '工作流已完成' : '平台正在处理水密工作流'
    : '平台正在处理水密工作流'
  const phaseElapsedSeconds = session?.phase_elapsed_ms == null
    ? null
    : (session.phase_elapsed_ms / 1000).toFixed(1)
  const prolongedPhase =
    session?.status === 'running' &&
    session.phase_elapsed_ms != null &&
    session.phase_elapsed_ms >= 180_000
  const fluentCallTimedOut =
    session?.status === 'failed' &&
    session.message.includes('没有返回')

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
      setManualTakeover(false)
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
      setManualTakeover(false)
    } finally {
      setBusy(false)
    }
  }

  const retryPreparation = async (): Promise<void> => {
    if (!sessionId) return
    setBusy(true)
    try {
      setSession(await fluentAiService.meshingLive.retryPrepare(sessionId))
    } catch (retryError) {
      message.error(retryError instanceof Error ? retryError.message : String(retryError))
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

  const pickMesh = async (): Promise<void> => {
    const path = await fluentAiService.meshingLive.pickMeshFile()
    if (path) setMeshPath(path)
  }

  const archiveMesh = async (): Promise<void> => {
    if (!meshPath.trim()) {
      message.warning('请先选择 Fluent 保存的网格文件。')
      return
    }
    setArchiving(true)
    try {
      const record = await fluentAiService.meshingLive.archive(sessionId, {
        mesh_path: meshPath.trim(),
        modeling_notes: modelingNotes,
      })
      setArchives((current) => [record, ...current])
      message.success('网格和配置差异已归档。')
    } catch (archiveError) {
      message.error(archiveError instanceof Error ? archiveError.message : String(archiveError))
    } finally {
      setArchiving(false)
    }
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
    const boundaryTypeOptions = currentTask.arguments.find(
      (candidate) => candidate.name === 'boundary_allowed_type_list',
    )?.default_value
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
            allowedValuesOverride={
              argument.name === 'boundary_zone_type_list' && Array.isArray(boundaryTypeOptions)
                ? (boundaryTypeOptions as MeshingPresetValue[])
                : undefined
            }
            value={values[key] ?? null}
            disabled={
              !manualTakeover ||
              busy ||
              session.status === 'running' ||
              session.status === 'stopped'
            }
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
              session.status === 'failed'
                ? 'red'
                : session.status === 'starting'
                ? 'gold'
                : session.status === 'running'
                  ? 'processing'
                  : session.connection?.connected
                    ? 'green'
                    : 'red'
            }
          >
            {session.status === 'starting'
              ? t('meshing.liveStarting')
              : session.status === 'failed'
                ? '准备失败'
              : session.status === 'running'
                ? currentModel?.status === 'importing'
                  ? t('meshing.liveImporting')
                  : t('meshing.liveProcessing')
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
        {pollError ? (
          <Alert
            type="warning"
            showIcon
            message="实时状态刷新受阻"
            description={pollError}
          />
        ) : null}
        {session.native_task_poll_error ? (
          <Alert
            type="warning"
            showIcon
            message="Fluent 当前步骤自动检测受阻"
            description={session.native_task_poll_error}
          />
        ) : null}
        {session.message ? (
          <Alert
            type={session.status === 'failed' ? 'error' : 'info'}
            showIcon
            message={session.message}
          />
        ) : null}
        {currentModel?.status === 'importing' ? (
          <Alert
            type="info"
            showIcon
            message={`正在导入目标几何：${currentModel.name}`}
            description="Fluent 已启动，平台正在导入并检查几何文件。导入完成后会自动进入工作流。"
          />
        ) : null}
        <Alert
          type={session.phase === 'failed' ? 'error' : prolongedPhase ? 'warning' : 'info'}
          showIcon
          message={phaseLabel}
          description={
            fluentCallTimedOut
              ? 'Fluent 当前请求仍未返回。平台已停止后续自动步骤；请先检查 Fluent 控制台，确认请求结束后再重新连接。'
              : session.status === 'running'
              ? prolongedPhase
                ? `本阶段已运行 ${phaseElapsedSeconds} 秒。平台正在等待当前 Fluent 请求；请求返回后会自动继续后续准备，且不会重复提交。请查看 Fluent 控制台是否有错误。`
                : phaseElapsedSeconds == null
                  ? '当前后端没有提供阶段计时。自动准备仍在继续，网格只会在面网格设置就绪后由你点击生成。'
                  : `本阶段已运行 ${phaseElapsedSeconds} 秒。Fluent 返回后，平台会自动继续准备；网格只会在面网格设置就绪后由你点击生成。`
              : '平台按任务顺序写入并回读参数。网格只在你点击对应生成按钮后开始生成。'
          }
          action={
            session.phase === 'failed' ? (
              fluentCallTimedOut ? null : (
                <Button size="small" onClick={() => void retryPreparation()} loading={busy}>重试准备</Button>
              )
            ) : session.phase === 'surface_ready' || session.phase === 'volume_ready' ? (
              <Button type="primary" size="small" onClick={() => void executeCurrentStep()} loading={busy}>
                {session.phase === 'surface_ready' ? '生成面网格' : '生成体网格'}
              </Button>
            ) : undefined
          }
        />
        <Button onClick={() => setManualTakeover((current) => !current)}>
          {manualTakeover ? '结束人工接管' : '人工接管平台操作'}
        </Button>
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

        <Card size="small" title="归档网格结果">
          <Space direction="vertical" size={10} className="full-width">
            <Typography.Text type="secondary">
              在 Fluent 中保存 .msh 或
              .msh.h5，然后在这里关联文件。平台会复制网格，并生成参数差异记录。
            </Typography.Text>
            <Space.Compact className="full-width">
              <Input
                value={meshPath}
                onChange={(event) => setMeshPath(event.target.value)}
                placeholder="Fluent 保存的网格文件路径"
              />
              <Button onClick={() => void pickMesh()}>浏览</Button>
            </Space.Compact>
            <Input.TextArea
              value={modelingNotes}
              onChange={(event) => setModelingNotes(event.target.value)}
              rows={3}
              placeholder="建模笔记（可选）"
            />
            <Button type="primary" loading={archiving} onClick={() => void archiveMesh()}>
              关联网格并生成记录
            </Button>
            {archives.map((record) => (
              <Alert
                key={record.id}
                type="success"
                showIcon
                message={`已归档 ${record.mesh_path}`}
                description={`差异 ${record.difference_count} 项；无法比较 ${record.unavailable_count} 项。可读记录：${record.record_markdown_path}；结构化记录：${record.record_json_path}`}
              />
            ))}
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
                  onClick={manualTakeover ? () => void enterStep(index) : undefined}
                  disabled={
                    !manualTakeover ||
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
              {currentTask.python_name === 'update_boundaries' ? (
                <Typography.Text type="secondary">
                  “几何区域名称”和“边界类型”按相同顺序逐项对应。模板中的成对设置会在进入此步骤时写入
                  Fluent。
                </Typography.Text>
              ) : null}
              {currentStep.duration_ms != null ? (
                <Typography.Text type="secondary">
                  {t('meshing.liveDuration', {
                    seconds: (currentStep.duration_ms / 1000).toFixed(1),
                  })}
                </Typography.Text>
              ) : null}
              {currentTask.child_template ? (
                <Space wrap className="meshing-live-add-child">
                  <Input
                    value={newChildName}
                    placeholder={t('meshing.liveChildNamePlaceholder')}
                    onChange={(event) => setNewChildName(event.target.value)}
                    disabled={!manualTakeover}
                    className="meshing-live-child-input"
                  />
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => void addChild()}
                    loading={busy}
                    disabled={!manualTakeover}
                  >
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
                icon={<SyncOutlined />}
                onClick={() => void overrideExternal()}
                disabled={!manualTakeover}
              >
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
