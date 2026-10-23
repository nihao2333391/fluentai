import { DeleteOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, App, Button, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type { MeshingAutomation, MeshingWorkflowReport, Model } from '../../../shared/contracts'
import { EmptyState, ErrorState, LoadingState, PageContent } from '../components/PageState'
import { localizedRuntimeMessage } from '../i18n/runtimeMessages'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

const MESHING_GEOMETRY_EXTENSIONS = [
  '.dsco',
  '.scdoc',
  '.step',
  '.stp',
  '.iges',
  '.igs',
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
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyReport, setApplyReport] = useState<MeshingWorkflowReport | null>(null)

  const fetchData = async (): Promise<[MeshingAutomation[], Model[]]> =>
    Promise.all([fluentAiService.meshingAutomations.list(), fluentAiService.models.list()])

  const load = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const [nextAutomations, nextModels] = await fetchData()
      setAutomations(nextAutomations)
      setModels(nextModels)
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
      .then(([nextAutomations, nextModels]) => {
        if (!active) return
        setAutomations(nextAutomations)
        setModels(nextModels)
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

  const openApply = (automation: MeshingAutomation): void => {
    setApplyAutomation(automation)
    setSelectedModelId(automation.reference_model_id)
    setApplyReport(null)
  }

  const closeApply = (): void => {
    if (applying) return
    setApplyAutomation(null)
    setSelectedModelId(null)
    setApplyReport(null)
  }

  const apply = async (): Promise<void> => {
    if (!applyAutomation) return
    if (!selectedModelId) {
      message.warning(t('meshing.selectApplyModel'))
      return
    }
    setApplying(true)
    setApplyReport(null)
    try {
      const report = await fluentAiService.meshingAutomations.apply(applyAutomation.id, {
        model_id: selectedModelId,
        connection: null,
        import_geometry: true,
      })
      setApplyReport(report)
      if (report.status === 'success') {
        message.success(t('meshing.applySuccess'))
      } else {
        message.error(localizedRuntimeMessage(t, report.message))
      }
    } catch (applyError) {
      message.error(applyError instanceof Error ? applyError.message : String(applyError))
    } finally {
      setApplying(false)
    }
  }

  const geometryModels = models.filter(isMeshingGeometry)

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
          {preset.workflow_type === 'watertight'
            ? t('meshing.watertight')
            : t('meshing.faultTolerant')}
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
      title: t('common.updated'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 200,
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
            icon={<PlayCircleOutlined />}
            aria-label={t('common.apply')}
            onClick={() => openApply(record)}
          />
          <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(record)} />
        </Space>
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

      <Modal
        open={applyAutomation !== null}
        title={t('meshing.applyTitle', { name: applyAutomation?.name ?? '' })}
        okText={t('common.apply')}
        cancelText={t('common.cancel')}
        confirmLoading={applying}
        onOk={() => void apply()}
        onCancel={closeApply}
        maskClosable={!applying}
        closable={!applying}
      >
        <Space direction="vertical" size={14} className="full-width">
          <Typography.Paragraph type="secondary" className="meshing-apply-note">
            {t('meshing.applyDescription')}
          </Typography.Paragraph>
          <Select
            value={selectedModelId}
            onChange={setSelectedModelId}
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
          {applyReport ? (
            <Alert
              type={applyReport.status === 'success' ? 'success' : 'error'}
              showIcon
              message={
                applyReport.status === 'success'
                  ? t('meshing.applyVerified', {
                      count: applyReport.apply_report?.results.length ?? 0,
                    })
                  : localizedRuntimeMessage(t, applyReport.message)
              }
              description={
                <Space direction="vertical" size={6}>
                  <span>{t('meshing.applyStoppedBefore')}</span>
                  {applyReport.apply_report?.missing_names.length ? (
                    <Space wrap>
                      {applyReport.apply_report.missing_names.map((name) => (
                        <Tag color="red" key={name}>
                          {name}
                        </Tag>
                      ))}
                    </Space>
                  ) : null}
                </Space>
              }
            />
          ) : null}
        </Space>
      </Modal>
    </PageContent>
  )
}
