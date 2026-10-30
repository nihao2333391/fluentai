import {
  DeleteOutlined,
  EditOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { App, Button, Card, Checkbox, Descriptions, Empty, Input, Modal, Progress, Select, Space, Tag, Tooltip, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type { MeshingAutomation, MeshingTask, MeshingTaskHistory, Model, PartCategory } from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

const MESHING_GEOMETRY_EXTENSIONS = [
  '.cas',
  '.msh',
  '.dsco',
  '.scdoc',
  '.scdocx',
  '.step',
  '.stp',
  '.stpz',
  '.iges',
  '.igs',
  '.jt',
  '.3dxml',
  '.catpart',
  '.catproduct',
  '.sldprt',
  '.sldasm',
  '.ipt',
  '.iam',
  '.prt',
  '.asm',
  '.par',
  '.stl',
  '.pmdb',
  '.fmd',
  '.tgf',
  '.x_t',
  '.x_b',
  '.sat',
  '.sab',
]

const isMeshingGeometry = (model: Model): boolean =>
  MESHING_GEOMETRY_EXTENSIONS.some((extension) =>
    model.file_path.toLocaleLowerCase().endsWith(extension),
  )

export function MeshingAutomationsPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [automations, setAutomations] = useState<MeshingAutomation[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applyAutomation, setApplyAutomation] = useState<MeshingAutomation | null>(null)
  const [selectedModelIds, setSelectedModelIds] = useState<number[]>([])
  const [applying, setApplying] = useState(false)
  const [categories, setCategories] = useState<PartCategory[]>([])
  const [tasks, setTasks] = useState<MeshingTask[]>([])
  const [categoryId, setCategoryId] = useState('')
  const [newCategoryName, setNewCategoryName] = useState('')
  const [createCategoryOpen, setCreateCategoryOpen] = useState(false)
  const [creatingCategory, setCreatingCategory] = useState(false)
  const [editingDirectories, setEditingDirectories] = useState(false)
  const [renamingCategory, setRenamingCategory] = useState<PartCategory | null>(null)
  const [renameCategoryName, setRenameCategoryName] = useState('')
  const [savingCategoryName, setSavingCategoryName] = useState(false)
  const [showDeletedTasks, setShowDeletedTasks] = useState(false)
  const [historyTask, setHistoryTask] = useState<MeshingTaskHistory | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [deleteTask, setDeleteTask] = useState<MeshingTask | null>(null)
  const [cleanupArtifacts, setCleanupArtifacts] = useState(false)

  const fetchData = async (): Promise<[MeshingAutomation[], Model[], PartCategory[], MeshingTask[]]> =>
    Promise.all([
      fluentAiService.meshingAutomations.list(),
      fluentAiService.models.list(),
      fluentAiService.categories.list(),
      fluentAiService.meshingTasks.list(showDeletedTasks),
    ])

  const load = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const [nextAutomations, nextModels, nextCategories, nextTasks] = await fetchData()
      setAutomations(nextAutomations)
      setModels(nextModels)
      setCategories(nextCategories)
      setTasks(nextTasks)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (sidecarState !== 'ready') return
    let active = true
    void fetchData()
      .then(([nextAutomations, nextModels, nextCategories, nextTasks]) => {
        if (!active) return
        setAutomations(nextAutomations)
        setModels(nextModels)
        setCategories(nextCategories)
        setTasks(nextTasks)
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
  }, [sidecarState, showDeletedTasks])

  useEffect(() => {
    if (categoryId || categories.length === 0) return
    const initialCategory =
      categories.find((category) => !category.is_system && category.template_count > 0) ??
      categories.find((category) => category.id === 'uncategorized') ??
      categories[0]
    setCategoryId(initialCategory.id)
  }, [categories, categoryId])

  const remove = (automation: MeshingAutomation): void => {
    modal.confirm({
      title: `${t('common.delete')} ${automation.name}`,
      onOk: async () => {
        await fluentAiService.meshingAutomations.delete(automation.id)
        await load()
      },
    })
  }

  const createCategory = async (): Promise<void> => {
    const name = newCategoryName.trim()
    if (!name) return
    setCreatingCategory(true)
    try {
      const category = await fluentAiService.categories.create({ name, description: '' })
      setNewCategoryName('')
      setCreateCategoryOpen(false)
      await load()
      setCategoryId(category.id)
      message.success(`目录“${category.name}”已创建。`)
    } catch (createError) {
      message.error(createError instanceof Error ? createError.message : String(createError))
    } finally {
      setCreatingCategory(false)
    }
  }

  const openRenameCategory = (category: PartCategory): void => {
    setRenamingCategory(category)
    setRenameCategoryName(category.name)
  }

  const renameCategory = async (): Promise<void> => {
    if (!renamingCategory) return
    const name = renameCategoryName.trim()
    if (!name || name === renamingCategory.name) return
    setSavingCategoryName(true)
    try {
      const updated = await fluentAiService.categories.rename(renamingCategory.id, name)
      setCategories((current) =>
        current.map((category) => (category.id === updated.id ? updated : category)),
      )
      setRenamingCategory(null)
      setRenameCategoryName('')
      message.success(`目录已重命名为“${updated.name}”。`)
    } catch (renameError) {
      message.error(renameError instanceof Error ? renameError.message : String(renameError))
    } finally {
      setSavingCategoryName(false)
    }
  }

  const deleteCategory = (category: PartCategory): void => {
    if (category.is_system || category.template_count > 0) return
    modal.confirm({
      title: `删除目录“${category.name}”？`,
      content: '此目录为空。删除后无法恢复。',
      okText: '删除目录',
      cancelText: t('common.cancel'),
      okType: 'danger',
      onOk: async () => {
        try {
          await fluentAiService.categories.delete(category.id)
          const nextCategories = categories.filter((item) => item.id !== category.id)
          setCategories(nextCategories)
          if (categoryId === category.id) setCategoryId(nextCategories[0]?.id ?? '')
          message.success(`目录“${category.name}”已删除。`)
        } catch (deleteError) {
          message.error(deleteError instanceof Error ? deleteError.message : String(deleteError))
        }
      },
    })
  }

  const openApply = (automation: MeshingAutomation): void => {
    setApplyAutomation(automation)
    setSelectedModelIds([])
  }

  const closeApply = (): void => {
    if (applying) return
    setApplyAutomation(null)
    setSelectedModelIds([])
  }

  const apply = async (): Promise<void> => {
    if (!applyAutomation) return
    if (selectedModelIds.length === 0) {
      message.warning(t('meshing.selectApplyModel'))
      return
    }
    setApplying(true)
    try {
      const session = await fluentAiService.meshingLive.start({
        automation_id: applyAutomation.id,
        model_ids: selectedModelIds,
        connection: null,
      })
      message.success(t('meshing.liveStarted'))
      navigate(`/meshing/live/${session.session_id}`)
    } catch (applyError) {
      const detail = applyError instanceof Error ? applyError.message : String(applyError)
      message.error(/timeout|aborted/i.test(detail) ? t('meshing.liveStartTimeout') : detail)
    } finally {
      setApplying(false)
    }
  }

  const openTaskHistory = async (task: MeshingTask): Promise<void> => {
    setHistoryLoading(true)
    try {
      const history = await fluentAiService.meshingTasks.history(
        task.id,
        Boolean(task.deleted_at),
      )
      setHistoryTask(history)
    } catch (historyError) {
      message.error(historyError instanceof Error ? historyError.message : String(historyError))
    } finally {
      setHistoryLoading(false)
    }
  }

  const confirmDeleteTask = async (): Promise<void> => {
    if (!deleteTask) return
    try {
      const result = await fluentAiService.meshingTasks.delete(
        deleteTask.id,
        cleanupArtifacts,
      )
      message.success(
        `${result.message} 保留 ${result.files_retained} 个文件，清理 ${result.files_deleted} 个文件。`,
      )
      setDeleteTask(null)
      setCleanupArtifacts(false)
      await load()
    } catch (deleteError) {
      message.error(deleteError instanceof Error ? deleteError.message : String(deleteError))
    }
  }

  const geometryModels = models.filter(isMeshingGeometry)
  const visibleAutomations = automations.filter((item) => item.category_id === categoryId)
  const selectedCategory = categories.find((category) => category.id === categoryId)
  const visibleCategories = categories.filter(
    (category) => !category.is_system || category.template_count > 0,
  )

  const taskStatus: Record<MeshingTask['status'], { label: string; color: string }> = {
    queued: { label: '排队中', color: 'blue' },
    preparing: { label: '准备中', color: 'processing' },
    waiting_surface: { label: '等待面网格', color: 'green' },
    waiting_volume: { label: '等待体网格', color: 'green' },
    completed: { label: '已完成', color: 'success' },
    failed: { label: '失败', color: 'error' },
    stopped: { label: '已停止', color: 'default' },
    interrupted: { label: '已中断', color: 'warning' },
  }

  const stagePercent = (status: MeshingTask['surface_mesh_status']): number => {
    if (status === 'completed' || status === 'failed') return 100
    if (status === 'running') return 70
    if (status === 'ready') return 45
    return 0
  }

  const renderTemplateCard = (automation: MeshingAutomation) => (
    <Card key={automation.id} className="template-library-card" size="small">
      <div className="template-card-heading">
        <div>
          <Typography.Title level={5}>{automation.name}</Typography.Title>
          <Typography.Text type="secondary">
            {automation.description || '暂无模板说明'}
          </Typography.Text>
        </div>
        <Tag color={automation.status === 'active' ? 'green' : 'default'}>
          {automation.status === 'active' ? `已发布 v${automation.published_revision ?? automation.revision}` : '草稿'}
        </Tag>
      </div>
      <Space wrap size={[8, 8]} className="template-card-meta">
        <Tag color={automation.preset.workflow_type === 'watertight' ? 'blue' : 'purple'}>
          {automation.preset.workflow_type === 'watertight'
            ? t('meshing.watertight')
            : t('meshing.faultTolerant')}
        </Tag>
        <Typography.Text type="secondary">{automation.preset.items.length} 项预设</Typography.Text>
        <Typography.Text type="secondary">
          更新于 {new Date(automation.updated_at).toLocaleDateString()}
        </Typography.Text>
      </Space>
      <div className="template-card-actions">
        <Space wrap>
          {automation.status !== 'active' ? (
            <Button onClick={async () => { await fluentAiService.meshingAutomations.publish(automation.id); await load() }}>
              发布模板
            </Button>
          ) : null}
          <Button aria-label="编辑" icon={<EditOutlined />} onClick={() => navigate(`/meshing/${automation.id}/edit`)}>
            编辑
          </Button>
          <Button
            type="primary"
            aria-label="应用"
            icon={<PlayCircleOutlined />}
            disabled={automation.status !== 'active' || !automation.published_revision}
            onClick={() => openApply(automation)}
          >
            应用
          </Button>
          <Button danger icon={<DeleteOutlined />} aria-label={`删除 ${automation.name}`} onClick={() => remove(automation)} />
        </Space>
      </div>
    </Card>
  )

  const renderTaskCard = (task: MeshingTask) => {
    const canEnter = Boolean(
      task.session_id && !task.deleted_at &&
      !['completed', 'stopped', 'interrupted'].includes(task.status),
    )
    const content = (
      <>
        <div className="task-card-heading">
          <div>
            <Typography.Text strong>{task.automation_name}</Typography.Text>
            <Typography.Text type="secondary">{task.model_names.join('、')} · v{task.template_revision}</Typography.Text>
          </div>
          <Tag color={task.deleted_at ? 'default' : taskStatus[task.status].color}>
            {task.deleted_at ? '已删除' : taskStatus[task.status].label}
          </Tag>
        </div>
        <div className="task-stage-grid">
          {([
            ['面网格', task.surface_mesh_status],
            ['体网格', task.volume_mesh_status],
          ] as const).map(([label, status]) => (
            <div key={label} className="task-stage-item">
              <Typography.Text type="secondary">{label}</Typography.Text>
              <Progress
                percent={stagePercent(status)}
                size="small"
                showInfo={false}
                status={status === 'failed' ? 'exception' : 'normal'}
              />
            </div>
          ))}
        </div>
        <div className="task-card-footer">
          <Typography.Text type="secondary">更新于 {new Date(task.updated_at).toLocaleString()}</Typography.Text>
          <Space size={4}>
            <Button type="link" onClick={(event) => { event.stopPropagation(); void openTaskHistory(task) }}>
              查看记录
            </Button>
            {canEnter ? (
              <Button type="link" onClick={(event) => { event.stopPropagation(); navigate(`/meshing/live/${task.session_id}`) }}>
                进入任务
              </Button>
            ) : null}
            {!task.deleted_at ? (
              <Button danger type="link" onClick={(event) => { event.stopPropagation(); setDeleteTask(task); setCleanupArtifacts(false) }}>
                删除
              </Button>
            ) : null}
          </Space>
        </div>
      </>
    )
    return (
      <Card
        key={task.id}
        size="small"
        className={`task-process-card${canEnter ? ' task-process-card-clickable' : ''}`}
        onClick={canEnter ? () => navigate(`/meshing/live/${task.session_id}`) : undefined}
        hoverable={canEnter}
      >
        {content}
      </Card>
    )
  }

  return (
    <PageContent
      title={t('meshing.listTitle')}
      description={t('meshing.listDescription')}
      actions={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            {t('common.reload')}
          </Button>
          <Button onClick={() => setCreateCategoryOpen(true)}>新建目录</Button>
        </Space>
      }
    >
      {sidecarState === 'error' ? (
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={t('errors.sidecarErrorDescription')}
          retryLabel={t('common.reload')}
          onRetry={() => void load()}
        />
      ) : loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={error}
          retryLabel={t('common.reload')}
          onRetry={() => void load()}
        />
      ) : (
        <div className={`template-library-layout${tasks.length === 0 && !showDeletedTasks ? ' template-library-layout-empty-tasks' : ''}`}>
          <section className="template-library-panel">
            <aside className="template-directory-rail">
              <div className="template-directory-heading">
                <div>
                  <Typography.Text strong>零件目录</Typography.Text>
                  <Typography.Text type="secondary">{visibleCategories.length} 个目录</Typography.Text>
                </div>
                <Space size={4} className="template-directory-tools">
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    aria-label="编辑目录"
                    aria-pressed={editingDirectories}
                    onClick={() => setEditingDirectories((editing) => !editing)}
                  >
                    {editingDirectories ? '完成' : '编辑目录'}
                  </Button>
                  <Button
                    type="text"
                    icon={<PlusOutlined />}
                    aria-label="新建目录"
                    onClick={() => setCreateCategoryOpen(true)}
                  />
                </Space>
              </div>
              <div className="template-directory-list">
                {visibleCategories.map((category) => (
                  <div
                    className={`template-directory-row${editingDirectories ? ' is-editing' : ''}`}
                    key={category.id}
                  >
                    <Button
                      type={category.id === categoryId ? 'primary' : 'text'}
                      className="template-directory-button"
                      icon={<FolderOutlined />}
                      onClick={() => setCategoryId(category.id)}
                    >
                      <span className="template-directory-name" title={category.name}>
                        {category.name}
                      </span>
                      <Tag className="template-directory-count">{category.template_count}</Tag>
                    </Button>
                    {editingDirectories && !category.is_system ? (
                      <Space size={0} className="template-directory-actions">
                        <Button
                          type="text"
                          className="template-directory-rename"
                          icon={<EditOutlined />}
                          aria-label={`重命名目录 ${category.name}`}
                          title="重命名目录"
                          onClick={() => openRenameCategory(category)}
                        />
                        <Tooltip
                          title={
                            category.template_count > 0
                              ? '请先移走或删除目录中的模板'
                              : '删除目录'
                          }
                        >
                          <Button
                            type="text"
                            danger
                            className="template-directory-delete"
                            icon={<DeleteOutlined />}
                            aria-label={`删除目录 ${category.name}`}
                            disabled={category.template_count > 0}
                            onClick={() => deleteCategory(category)}
                          />
                        </Tooltip>
                      </Space>
                    ) : editingDirectories ? (
                      <span className="template-directory-actions-placeholder" aria-hidden="true" />
                    ) : null}
                  </div>
                ))}
              </div>
            </aside>
            <div className="template-list-pane">
              <div className="template-list-heading">
                <div>
                  <Typography.Title level={4}>{selectedCategory?.name ?? '模板'}</Typography.Title>
                  <Typography.Text type="secondary">
                    {visibleAutomations.length} 个模板 · 新建模板会自动使用此目录名称作为模型类别
                  </Typography.Text>
                </div>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  disabled={!categoryId}
                  onClick={() => navigate(`/meshing/create?category_id=${encodeURIComponent(categoryId)}`)}
                >
                  新建模板
                </Button>
              </div>
              {visibleAutomations.length === 0 ? (
                <Empty
                  className="template-library-empty"
                  description={
                    <Space direction="vertical" size={4}>
                      <Typography.Text strong>此目录还没有模板</Typography.Text>
                      <Typography.Text type="secondary">在当前目录中新建模板，模型类别会自动填入“{selectedCategory?.name ?? ''}”。</Typography.Text>
                    </Space>
                  }
                />
              ) : (
                <div className="template-card-list">{visibleAutomations.map(renderTemplateCard)}</div>
              )}
            </div>
          </section>
          {tasks.length > 0 || showDeletedTasks ? (
            <Card
              title="任务进程"
              className="template-task-panel"
              extra={
                <Space>
                  <Checkbox
                    checked={showDeletedTasks}
                    onChange={(event) => {
                      setShowDeletedTasks(event.target.checked)
                      void fluentAiService.meshingTasks.list(event.target.checked).then(setTasks)
                    }}
                  >
                    显示已删除
                  </Checkbox>
                  <Button type="link" onClick={() => void load()}>刷新</Button>
                </Space>
              }
            >
              {tasks.length === 0 ? (
                <Typography.Text type="secondary">当前没有任务记录。</Typography.Text>
              ) : (
                <div className="task-process-list">{tasks.map(renderTaskCard)}</div>
              )}
            </Card>
          ) : null}
        </div>
      )}

      <Modal
        open={createCategoryOpen}
        title="新建零件目录"
        okText="创建目录"
        cancelText={t('common.cancel')}
        confirmLoading={creatingCategory}
        okButtonProps={{ disabled: newCategoryName.trim().length === 0 }}
        onOk={() => void createCategory()}
        onCancel={() => {
          if (creatingCategory) return
          setCreateCategoryOpen(false)
          setNewCategoryName('')
        }}
        destroyOnHidden
      >
        <Input
          autoFocus
          value={newCategoryName}
          onChange={(event) => setNewCategoryName(event.target.value)}
          onPressEnter={() => void createCategory()}
          maxLength={120}
          placeholder="输入目录名称"
        />
        <Typography.Paragraph type="secondary" className="template-directory-modal-hint">
          每个目录直接收纳模板。目录名称会自动成为其中模板的模型类别。
        </Typography.Paragraph>
      </Modal>

      <Modal
        open={renamingCategory !== null}
        title="重命名目录"
        okText="保存名称"
        cancelText={t('common.cancel')}
        confirmLoading={savingCategoryName}
        okButtonProps={{
          disabled:
            renameCategoryName.trim().length === 0 ||
            renameCategoryName.trim() === renamingCategory?.name,
        }}
        onOk={() => void renameCategory()}
        onCancel={() => {
          if (savingCategoryName) return
          setRenamingCategory(null)
          setRenameCategoryName('')
        }}
        destroyOnHidden
      >
        <Input
          autoFocus
          aria-label="目录名称"
          value={renameCategoryName}
          onChange={(event) => setRenameCategoryName(event.target.value)}
          onPressEnter={() => void renameCategory()}
          maxLength={120}
          placeholder="输入目录名称"
        />
        <Typography.Paragraph type="secondary" className="template-directory-modal-hint">
          目录中的模板会继续保留，并自动使用新的目录名称作为模型类别。
        </Typography.Paragraph>
      </Modal>

      <Modal
        open={applyAutomation !== null}
        title={t('meshing.applyTitle', { name: applyAutomation?.name ?? '' })}
        okText={t('meshing.liveApplyButton')}
        cancelText={t('common.cancel')}
        confirmLoading={applying}
        onOk={() => void apply()}
        onCancel={closeApply}
        maskClosable={!applying}
        closable={!applying}
      >
        <Space direction="vertical" size={14} className="full-width">
          <Typography.Paragraph type="secondary" className="meshing-apply-note">
            {t('meshing.liveApplyDescription')}
          </Typography.Paragraph>
          <Select
            mode="multiple"
            value={selectedModelIds}
            onChange={setSelectedModelIds}
            className="full-width"
            placeholder={t('meshing.selectApplyModel')}
            options={geometryModels.map((model) => ({
              value: model.id,
              label: `${model.name} — ${model.file_path}`,
            }))}
            notFoundContent={t('meshing.noGeometryModels')}
            showSearch
            optionFilterProp="label"
          />
        </Space>
      </Modal>
      <Modal
        open={historyTask !== null}
        title="任务历史与产物"
        footer={<Button onClick={() => setHistoryTask(null)}>关闭</Button>}
        onCancel={() => setHistoryTask(null)}
        width={760}
        confirmLoading={historyLoading}
      >
        {historyTask ? <Space direction="vertical" size={16} className="full-width">
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="任务">{historyTask.task.automation_name}</Descriptions.Item>
            <Descriptions.Item label="模板版本">v{historyTask.task.template_revision || '未知'}</Descriptions.Item>
            <Descriptions.Item label="模型">{historyTask.task.model_names.join('、')}</Descriptions.Item>
            <Descriptions.Item label="状态">{historyTask.task.deleted_at ? '已删除' : historyTask.task.status}</Descriptions.Item>
          </Descriptions>
          <Typography.Text strong>任务产物</Typography.Text>
          {historyTask.artifacts.length === 0 ? <Typography.Text type="secondary">此任务还没有归档文件。</Typography.Text> : historyTask.artifacts.map((artifact) => <Space key={artifact.id} direction="vertical" size={0}>
            <Typography.Text>{({ mesh: '网格文件', record_json: 'JSON 参数记录', record_markdown: 'Markdown 报告', log: '日志', report: '报告' } as const)[artifact.kind]} · {artifact.status === 'retained' ? '已保留' : artifact.status === 'missing' ? '文件缺失' : '已清理'}</Typography.Text>
            <Typography.Text type="secondary" copyable>{artifact.file_path}</Typography.Text>
          </Space>)}
          <Typography.Text strong>任务事件</Typography.Text>
          {historyTask.events.length === 0 ? <Typography.Text type="secondary">暂无历史事件。</Typography.Text> : <Space direction="vertical" size={4} className="full-width">
            {historyTask.events.map((event) => <Typography.Text key={event.id} type="secondary">{new Date(event.created_at).toLocaleString()} · {event.message || event.event_type}</Typography.Text>)}
          </Space>}
        </Space> : null}
      </Modal>
      <Modal
        open={deleteTask !== null}
        title="删除任务记录"
        okText="删除任务"
        cancelText="取消"
        onOk={() => void confirmDeleteTask()}
        onCancel={() => setDeleteTask(null)}
      >
        <Space direction="vertical">
          <Typography.Text>删除后，历史任务会从默认列表隐藏，归属索引仍保留。</Typography.Text>
          <Checkbox checked={cleanupArtifacts} onChange={(event) => setCleanupArtifacts(event.target.checked)}>
            同时清理该任务独占的归档文件
          </Checkbox>
          {!cleanupArtifacts ? <Typography.Text type="secondary">默认保留网格文件和历史报告。</Typography.Text> : null}
        </Space>
      </Modal>
    </PageContent>
  )
}
