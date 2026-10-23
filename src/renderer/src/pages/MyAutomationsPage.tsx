import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Input,
  List,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type {
  Automation,
  Model,
  RecentSession,
  SyncLog,
  SyncLogDirection,
  SyncLogStatus,
} from '../../../shared/contracts'
import { EmptyState, ErrorState, LoadingState, PageContent } from '../components/PageState'
import { localizedRuntimeMessage } from '../i18n/runtimeMessages'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

export function MyAutomationsPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [automations, setAutomations] = useState<Automation[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [recentSession, setRecentSession] = useState<RecentSession | null>(null)
  const [logDirection, setLogDirection] = useState<SyncLogDirection | undefined>()
  const [logStatus, setLogStatus] = useState<SyncLogStatus | undefined>()
  const [logSearch, setLogSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applyAutomation, setApplyAutomation] = useState<Automation | null>(null)
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null)
  const [applying, setApplying] = useState(false)

  const fetchData = useCallback(
    (): Promise<[Automation[], Model[], SyncLog[], RecentSession]> =>
      Promise.all([
        fluentAiService.automations.list(),
        fluentAiService.models.list(),
        fluentAiService.syncLogs.list({
          limit: 20,
          direction: logDirection,
          status: logStatus,
          search: logSearch || undefined,
        }),
        fluentAiService.session.recent(),
      ]),
    [logDirection, logSearch, logStatus],
  )

  const loadData = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const [nextAutomations, nextModels, nextLogs, nextRecentSession] = await fetchData()
      setAutomations(nextAutomations)
      setModels(nextModels)
      setLogs(nextLogs)
      setRecentSession(nextRecentSession)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (sidecarState !== 'ready') {
      return
    }
    let active = true
    void fetchData()
      .then(([nextAutomations, nextModels, nextLogs, nextRecentSession]) => {
        if (active) {
          setAutomations(nextAutomations)
          setModels(nextModels)
          setLogs(nextLogs)
          setRecentSession(nextRecentSession)
        }
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : String(loadError))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [fetchData, sidecarState])

  const restoreRecentSession = (): void => {
    if (!recentSession?.model) {
      navigate('/models')
      return
    }
    if (recentSession.automation) {
      setApplyAutomation(recentSession.automation)
      setSelectedModelId(recentSession.model.id)
    }
  }

  const openApply = (automation: Automation): void => {
    setApplyAutomation(automation)
    const associatedModel = models.find((model) => model.automation_ids.includes(automation.id))
    setSelectedModelId(associatedModel?.id ?? models[0]?.id ?? null)
  }

  const applySelected = async (): Promise<void> => {
    if (!applyAutomation || !selectedModelId) {
      message.warning(t('pages.myAutomations.selectModelRequired'))
      return
    }
    setApplying(true)
    try {
      const report = await fluentAiService.workflows.applyAutomation(applyAutomation.id, {
        model_id: selectedModelId,
        load_case: true,
      })
      if (report.status === 'success') {
        message.success(t('pages.myAutomations.applied'))
        setApplyAutomation(null)
        await loadData()
      } else {
        modal.error({
          title: t('pages.myAutomations.failed'),
          content: localizedRuntimeMessage(t, report.message),
        })
      }
    } catch (applyError) {
      modal.error({
        title: t('pages.myAutomations.failed'),
        content: applyError instanceof Error ? applyError.message : String(applyError),
      })
    } finally {
      setApplying(false)
    }
  }

  const deleteAutomation = (automation: Automation): void => {
    modal.confirm({
      title: `${t('common.delete')} ${automation.name}`,
      onOk: async () => {
        await fluentAiService.automations.delete(automation.id)
        await loadData()
      },
    })
  }

  const columns: ColumnsType<Automation> = [
    {
      title: t('pages.automationCreate.name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{name}</Typography.Text>
          <Typography.Text type="secondary">{record.description}</Typography.Text>
        </Space>
      ),
    },
    {
      title: t('pages.automationCreate.settings'),
      dataIndex: 'preset',
      key: 'preset',
      render: (preset: Automation['preset']) => (
        <Tag color="blue">
          {t('pages.myAutomations.settingsCount', { count: preset.items.length })}
        </Tag>
      ),
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: Automation['status']) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>{t(`common.${status}`)}</Tag>
      ),
    },
    {
      title: t('common.updated'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 200,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: '',
      key: 'actions',
      width: 210,
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="primary"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => openApply(record)}
          >
            {t('common.apply')}
          </Button>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => navigate(`/automations/${record.id}/edit`)}
            aria-label={t('common.edit')}
          />
          <Button
            type="text"
            icon={<CopyOutlined />}
            onClick={() => navigate(`/automations/${record.id}/duplicate`)}
            aria-label={t('common.duplicate')}
          />
          <Button
            danger
            type="text"
            icon={<DeleteOutlined />}
            onClick={() => deleteAutomation(record)}
            aria-label={t('common.delete')}
          />
        </Space>
      ),
    },
  ]

  return (
    <PageContent
      title={t('pages.myAutomations.title')}
      description={t('pages.myAutomations.description')}
      actions={
        <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>
          {t('common.reload')}
        </Button>
      }
    >
      {sidecarState === 'error' ? (
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={t('errors.sidecarErrorDescription')}
          retryLabel={t('common.reload')}
          onRetry={() => void loadData()}
        />
      ) : loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={error}
          retryLabel={t('common.reload')}
          onRetry={() => void loadData()}
        />
      ) : automations.length === 0 ? (
        <EmptyState
          title={t('pages.myAutomations.emptyTitle')}
          description={t('pages.myAutomations.emptyDescription')}
        />
      ) : (
        <Space direction="vertical" size={18} className="full-width">
          {recentSession?.model ? (
            <Card
              title={t('pages.myAutomations.recentSession')}
              extra={
                recentSession.automation ? (
                  <Button type="primary" onClick={restoreRecentSession}>
                    {t('pages.myAutomations.restoreRecent')}
                  </Button>
                ) : undefined
              }
            >
              <Space direction="vertical" size={6}>
                <Typography.Text strong>{recentSession.model.name}</Typography.Text>
                <Typography.Text type="secondary">
                  {recentSession.automation?.name ??
                    recentSession.meshing_automation?.name ??
                    t('pages.myAutomations.noAutomation')}
                </Typography.Text>
                <Typography.Text type="secondary">
                  {recentSession.updated_at
                    ? new Date(recentSession.updated_at).toLocaleString()
                    : ''}
                </Typography.Text>
              </Space>
            </Card>
          ) : null}
          <Table
            rowKey="id"
            columns={columns}
            dataSource={automations}
            pagination={false}
            className="data-table-card"
          />
          <Card title={t('pages.myAutomations.recentLogs')}>
            <Space wrap className="log-filter-row">
              <Select
                allowClear
                value={logDirection}
                onChange={setLogDirection}
                placeholder={t('pages.myAutomations.filterDirection')}
                options={[
                  { value: 'apply', label: t('common.logDirections.apply') },
                  { value: 'write', label: t('common.logDirections.write') },
                  { value: 'read', label: t('common.logDirections.read') },
                  { value: 'sync', label: t('common.logDirections.sync') },
                  { value: 'pull', label: t('common.logDirections.pull') },
                ]}
                className="log-filter-select"
              />
              <Select
                allowClear
                value={logStatus}
                onChange={setLogStatus}
                placeholder={t('pages.myAutomations.filterStatus')}
                options={[
                  { value: 'success', label: t('common.success') },
                  { value: 'failed', label: t('common.failed') },
                ]}
                className="log-filter-select"
              />
              <Input.Search
                allowClear
                defaultValue={logSearch}
                placeholder={t('pages.myAutomations.searchLogs')}
                onSearch={setLogSearch}
                className="log-search"
              />
            </Space>
            {logs.length === 0 ? (
              <Typography.Text type="secondary">{t('common.notAvailable')}</Typography.Text>
            ) : (
              <List
                size="small"
                dataSource={logs}
                renderItem={(log) => (
                  <List.Item>
                    <Space wrap>
                      <Tag color={log.status === 'success' ? 'green' : 'red'}>
                        {t(`common.${log.status}`)}
                      </Tag>
                      <Tag>{t(`common.logDirections.${log.direction}`)}</Tag>
                      <Typography.Text>{localizedRuntimeMessage(t, log.message)}</Typography.Text>
                      <Typography.Text type="secondary">
                        {new Date(log.created_at).toLocaleString()}
                      </Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Space>
      )}

      <Modal
        open={applyAutomation !== null}
        title={`${t('pages.myAutomations.applyTitle')}: ${applyAutomation?.name ?? ''}`}
        okText={t('common.apply')}
        cancelText={t('common.cancel')}
        confirmLoading={applying}
        onOk={() => void applySelected()}
        onCancel={() => setApplyAutomation(null)}
      >
        <Space direction="vertical" size={16} className="full-width">
          {models.length === 0 ? (
            <Alert type="warning" showIcon message={t('pages.myAutomations.noModels')} />
          ) : null}
          <div>
            <Typography.Text strong>{t('pages.myAutomations.selectModel')}</Typography.Text>
            <Select
              className="full-width model-select"
              value={selectedModelId}
              onChange={setSelectedModelId}
              options={models.map((model) => ({ value: model.id, label: model.name }))}
              disabled={models.length === 0}
            />
          </div>
          <Alert type="info" showIcon message={t('pages.myAutomations.applying')} />
        </Space>
      </Modal>
    </PageContent>
  )
}
