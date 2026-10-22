import { DeleteOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, List, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Automation, Model, SyncLog } from '../../../shared/contracts'
import { EmptyState, ErrorState, LoadingState, PageContent } from '../components/PageState'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

export function MyAutomationsPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [automations, setAutomations] = useState<Automation[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applyAutomation, setApplyAutomation] = useState<Automation | null>(null)
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null)
  const [applying, setApplying] = useState(false)

  const fetchData = (): Promise<[Automation[], Model[], SyncLog[]]> =>
    Promise.all([
      fluentAiService.automations.list(),
      fluentAiService.models.list(),
      fluentAiService.syncLogs.list(8),
    ])

  const loadData = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const [nextAutomations, nextModels, nextLogs] = await fetchData()
      setAutomations(nextAutomations)
      setModels(nextModels)
      setLogs(nextLogs)
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
      .then(([nextAutomations, nextModels, nextLogs]) => {
        if (active) {
          setAutomations(nextAutomations)
          setModels(nextModels)
          setLogs(nextLogs)
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
  }, [sidecarState])

  const openApply = (automation: Automation): void => {
    setApplyAutomation(automation)
    setSelectedModelId(models[0]?.id ?? null)
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
          content: report.message,
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
        <Tag color="blue">{preset.items.length} settings</Tag>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: Automation['status']) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag>
      ),
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 200,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: '',
      key: 'actions',
      width: 140,
      render: (_, record) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => openApply(record)}
          >
            {t('common.apply')}
          </Button>
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
          <Table
            rowKey="id"
            columns={columns}
            dataSource={automations}
            pagination={false}
            className="data-table-card"
          />
          <Card title={t('pages.myAutomations.recentLogs')}>
            {logs.length === 0 ? (
              <Typography.Text type="secondary">{t('common.notAvailable')}</Typography.Text>
            ) : (
              <List
                size="small"
                dataSource={logs}
                renderItem={(log) => (
                  <List.Item>
                    <Space wrap>
                      <Tag color={log.status === 'success' ? 'green' : 'red'}>{log.status}</Tag>
                      <Tag>{log.direction}</Tag>
                      <Typography.Text>{log.message}</Typography.Text>
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
