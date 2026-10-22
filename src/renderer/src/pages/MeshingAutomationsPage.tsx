import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { App, Button, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type { MeshingAutomation } from '../../../shared/contracts'
import { EmptyState, ErrorState, LoadingState, PageContent } from '../components/PageState'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

export function MeshingAutomationsPage() {
  const { t } = useTranslation()
  const { modal } = App.useApp()
  const navigate = useNavigate()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [automations, setAutomations] = useState<MeshingAutomation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAutomations = (): Promise<MeshingAutomation[]> =>
    fluentAiService.meshingAutomations.list()

  const load = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      setAutomations(await fetchAutomations())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (sidecarState !== 'ready') return
    let active = true
    void fetchAutomations()
      .then((items) => {
        if (active) setAutomations(items)
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
  }, [sidecarState])

  const remove = (automation: MeshingAutomation): void => {
    modal.confirm({
      title: `${t('common.delete')} ${automation.name}`,
      onOk: async () => {
        await fluentAiService.meshingAutomations.delete(automation.id)
        await load()
      },
    })
  }

  const columns: ColumnsType<MeshingAutomation> = [
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
      title: t('meshing.workflowType'),
      dataIndex: 'preset',
      key: 'workflow',
      render: (preset: MeshingAutomation['preset']) => (
        <Tag color={preset.workflow_type === 'watertight' ? 'blue' : 'purple'}>
          {preset.workflow_type}
        </Tag>
      ),
    },
    {
      title: t('meshing.modelFamily'),
      dataIndex: 'model_family',
      key: 'model_family',
    },
    {
      title: t('meshing.optionCount'),
      dataIndex: 'preset',
      key: 'count',
      width: 120,
      render: (preset: MeshingAutomation['preset']) => preset.items.length,
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
      width: 70,
      render: (_, record) => (
        <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(record)} />
      ),
    },
  ]

  return (
    <PageContent
      title={t('meshing.listTitle')}
      description={t('meshing.listDescription')}
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            {t('common.reload')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/meshing/create')}
          >
            {t('meshing.createButton')}
          </Button>
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
      ) : automations.length === 0 ? (
        <EmptyState title={t('meshing.emptyTitle')} description={t('meshing.emptyDescription')} />
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={automations}
          pagination={false}
          className="data-table-card"
        />
      )}
    </PageContent>
  )
}
