import { ApiOutlined, DatabaseOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { App, Button, Space, Table, Typography } from 'antd'
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

const isSolverModel = (model: Model): boolean =>
  ['.cas', '.cas.h5', '.msh', '.msh.h5'].some((extension) =>
    model.file_path.toLocaleLowerCase().endsWith(extension),
  )

export function MyModelsPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [openingModelId, setOpeningModelId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchData = (): Promise<Model[]> => fluentAiService.models.list()

  const loadData = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const nextModels = await fetchData()
      setModels(nextModels)
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
      .then((nextModels) => {
        if (active) {
          setModels(nextModels)
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
      await loadData()
    } catch (importError) {
      message.error(importError instanceof Error ? importError.message : String(importError))
    } finally {
      setImporting(false)
    }
  }

  const openModel = async (model: Model): Promise<void> => {
    setOpeningModelId(model.id)
    try {
      const report = await fluentAiService.models.open(model.id, { load_case: true })
      if (report.status === 'success') {
        message.success(t('pages.myModels.opened'))
      } else {
        modal.error({ title: t('pages.myModels.openFailed'), content: report.message })
      }
    } catch (openError) {
      modal.error({
        title: t('pages.myModels.openFailed'),
        content: openError instanceof Error ? openError.message : String(openError),
      })
    } finally {
      setOpeningModelId(null)
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
      title: t('pages.myModels.created'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 190,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: '',
      key: 'actions',
      width: 70,
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="text"
            icon={<ApiOutlined />}
            disabled={!isSolverModel(record)}
            loading={openingModelId === record.id}
            aria-label={t('common.open')}
            onClick={() => void openModel(record)}
          />
        </Space>
      ),
    },
  ]

  return (
    <PageContent
      title={t('pages.myModels.title')}
      description={t('pages.myModels.description')}
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>
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
