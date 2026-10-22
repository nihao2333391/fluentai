import {
  ApiOutlined,
  DatabaseOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { App, Button, Checkbox, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Automation, Model } from '../../../shared/contracts'
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
  const [automations, setAutomations] = useState<Automation[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [openingModelId, setOpeningModelId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [associateModel, setAssociateModel] = useState<Model | null>(null)
  const [selectedAutomationId, setSelectedAutomationId] = useState<number | null>(null)
  const [isDefaultAutomation, setIsDefaultAutomation] = useState(true)
  const [savingAssociation, setSavingAssociation] = useState(false)

  const fetchData = (): Promise<[Model[], Automation[]]> =>
    Promise.all([fluentAiService.models.list(), fluentAiService.automations.list()])

  const loadData = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const [nextModels, nextAutomations] = await fetchData()
      setModels(nextModels)
      setAutomations(nextAutomations)
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
      .then(([nextModels, nextAutomations]) => {
        if (active) {
          setModels(nextModels)
          setAutomations(nextAutomations)
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

  const openAssociation = (model: Model): void => {
    setAssociateModel(model)
    setSelectedAutomationId(model.default_automation_id)
    setIsDefaultAutomation(true)
  }

  const saveAssociation = async (): Promise<void> => {
    if (!associateModel) return
    if (!selectedAutomationId) {
      message.warning(t('pages.myModels.selectAutomationRequired'))
      return
    }
    setSavingAssociation(true)
    try {
      await fluentAiService.models.associate(associateModel.id, {
        automationId: selectedAutomationId,
        isDefault: isDefaultAutomation,
      })
      message.success(t('pages.myModels.associated'))
      setAssociateModel(null)
      await loadData()
    } catch (associationError) {
      message.error(
        associationError instanceof Error ? associationError.message : String(associationError),
      )
    } finally {
      setSavingAssociation(false)
    }
  }

  const automationName = (automationId: number | null): string | null =>
    automationId === null
      ? null
      : (automations.find((automation) => automation.id === automationId)?.name ??
        `#${automationId}`)

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
      title: t('pages.myModels.selectAutomation'),
      dataIndex: 'default_automation_id',
      key: 'default_automation_id',
      width: 170,
      render: (automationId: number | null) => {
        const name = automationName(automationId)
        return name ? <Tag color="blue">{name}</Tag> : <Tag>None</Tag>
      },
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
      width: 130,
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
          <Button
            type="text"
            icon={<LinkOutlined />}
            aria-label={t('pages.myModels.automate')}
            onClick={() => openAssociation(record)}
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

      <Modal
        open={associateModel !== null}
        title={`${t('pages.myModels.automate')}: ${associateModel?.name ?? ''}`}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
        confirmLoading={savingAssociation}
        onOk={() => void saveAssociation()}
        onCancel={() => setAssociateModel(null)}
      >
        <Space direction="vertical" size={16} className="full-width">
          <Select
            className="full-width"
            value={selectedAutomationId}
            onChange={setSelectedAutomationId}
            placeholder={t('pages.myModels.selectAutomation')}
            options={automations.map((automation) => ({
              value: automation.id,
              label: automation.name,
            }))}
          />
          <Checkbox
            checked={isDefaultAutomation}
            onChange={(event) => setIsDefaultAutomation(event.target.checked)}
          >
            {t('pages.myModels.selectAutomation')}
          </Checkbox>
        </Space>
      </Modal>
    </PageContent>
  )
}
