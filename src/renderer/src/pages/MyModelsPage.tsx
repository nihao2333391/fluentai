import { DatabaseOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { App, Button, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Model } from '../../../shared/contracts'
import { EmptyState, ErrorState, LoadingState, PageContent } from '../components/PageState'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function MyModelsPage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchModels = (): Promise<Model[]> => fluentAiService.models.list()

  const loadModels = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      setModels(await fetchModels())
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
    void fetchModels()
      .then((items) => {
        if (active) setModels(items)
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

  const importModel = async (): Promise<void> => {
    setImporting(true)
    try {
      const selected = await fluentAiService.models.pickFile()
      if (!selected) return
      await fluentAiService.models.create({
        name: selected.fileName,
        fileToken: selected.fileToken,
        description: '',
        tags: [],
      })
      message.success(t('pages.myModels.imported'))
      await loadModels()
    } catch (importError) {
      message.error(importError instanceof Error ? importError.message : String(importError))
    } finally {
      setImporting(false)
    }
  }

  const columns: ColumnsType<Model> = [
    {
      title: t('pages.myModels.name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: t('pages.myModels.path'),
      dataIndex: 'file_path',
      key: 'file_path',
      ellipsis: true,
      render: (path: string) => (
        <Typography.Text type="secondary" copyable={{ text: path }}>
          {path}
        </Typography.Text>
      ),
    },
    {
      title: t('pages.myModels.size'),
      dataIndex: 'file_size',
      key: 'file_size',
      width: 110,
      render: (size: number) => formatBytes(size),
    },
    {
      title: 'Automation',
      dataIndex: 'default_automation_id',
      key: 'default_automation_id',
      width: 130,
      render: (automationId: number | null) =>
        automationId ? <Tag color="blue">#{automationId}</Tag> : <Tag>None</Tag>,
    },
    {
      title: t('pages.myModels.created'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 210,
      render: (value: string) => new Date(value).toLocaleString(),
    },
  ]

  return (
    <PageContent
      title={t('pages.myModels.title')}
      description={t('pages.myModels.description')}
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadModels()}>
            {t('common.reload')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={importing}
            onClick={() => void importModel()}
          >
            {importing ? t('pages.myModels.importing') : t('pages.myModels.importModel')}
          </Button>
        </Space>
      }
    >
      {sidecarState === 'error' ? (
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={t('errors.sidecarErrorDescription')}
          retryLabel={t('common.reload')}
          onRetry={() => void loadModels()}
        />
      ) : loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={error}
          retryLabel={t('common.reload')}
          onRetry={() => void loadModels()}
        />
      ) : models.length === 0 ? (
        <EmptyState
          title={t('pages.myModels.emptyTitle')}
          description={t('pages.myModels.emptyDescription')}
        />
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={models}
          pagination={false}
          className="data-table-card"
          locale={{ emptyText: <DatabaseOutlined /> }}
        />
      )}
    </PageContent>
  )
}
