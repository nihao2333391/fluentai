import {
  CalculatorOutlined,
  ExperimentOutlined,
  SaveOutlined,
  SettingOutlined,
  SlidersOutlined,
} from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type {
  FluentSettingGroup,
  PresetDocument,
  PresetItem,
  PresetValue,
  SettingCatalogEntry,
} from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

interface AutomationFormValues {
  name: string
  description: string
}

const GROUP_ICONS: Record<FluentSettingGroup, ReactNode> = {
  general: <SettingOutlined />,
  models: <ExperimentOutlined />,
  solution: <SlidersOutlined />,
  reference: <CalculatorOutlined />,
}

const defaultSettingValue = (entry: SettingCatalogEntry): PresetValue => {
  const known: Record<string, PresetValue> = {
    'solver.time': 'steady',
    'solver.type': 'pressure-based',
    'solver.velocity_formulation': 'absolute',
    'viscous.model': 'k-omega',
    'viscous.k_omega_model': 'sst',
    'reference.area': 1,
    'reference.density': 1.225,
    'reference.length': 1,
    'reference.velocity': 1,
    'reference.viscosity': 1.7894e-5,
  }
  if (entry.setting_id in known) return known[entry.setting_id]
  if (entry.setting_id.startsWith('residual.')) return 0.001
  if (entry.value_type === 'bool') return false
  if (entry.value_type === 'int') return 0
  if (entry.value_type === 'float') return entry.minimum ?? 0
  if (entry.allowed_values?.length) return entry.allowed_values[0]
  return ''
}

const formatOption = (value: PresetValue): string => {
  if (typeof value !== 'string') return String(value)
  return value
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function AutomationCreatePage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<AutomationFormValues>()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [catalog, setCatalog] = useState<SettingCatalogEntry[]>([])
  const [included, setIncluded] = useState<Record<string, boolean>>({})
  const [values, setValues] = useState<Record<string, PresetValue>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const initializeCatalog = (entries: SettingCatalogEntry[]): void => {
    setCatalog(entries)
    setValues((current) => {
      const next = { ...current }
      for (const entry of entries) {
        if (!(entry.setting_id in next)) {
          next[entry.setting_id] = defaultSettingValue(entry)
        }
      }
      return next
    })
  }

  const fetchCatalog = async (): Promise<SettingCatalogEntry[]> => fluentAiService.fluent.catalog()

  const loadCatalog = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      initializeCatalog(await fetchCatalog())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (sidecarState !== 'ready') return
    let active = true
    void fetchCatalog()
      .then((entries) => {
        if (active) {
          initializeCatalog(entries)
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

  const includedCount = Object.values(included).filter(Boolean).length

  const groups = useMemo(
    () => [
      { key: 'general', label: t('fluentGroups.general'), icon: GROUP_ICONS.general },
      { key: 'models', label: t('fluentGroups.models'), icon: GROUP_ICONS.models },
      { key: 'solution', label: t('fluentGroups.solution'), icon: GROUP_ICONS.solution },
      { key: 'reference', label: t('fluentGroups.reference'), icon: GROUP_ICONS.reference },
    ],
    [t],
  )

  const saveAutomation = async (formValues: AutomationFormValues): Promise<void> => {
    const selected = catalog.filter((entry) => included[entry.setting_id])
    if (selected.length === 0) {
      message.warning(t('pages.automationCreate.selectAtLeastOne'))
      return
    }

    setSaving(true)
    try {
      const items: PresetItem[] = selected.map((entry) => ({
        setting_id: entry.setting_id,
        type: entry.value_type,
        value: values[entry.setting_id],
        required: true,
      }))
      const preset: PresetDocument = {
        schema_version: 1,
        fluent_version: '25.2.0',
        items,
      }
      const validation = await fluentAiService.fluent.validatePreset(preset)
      if (!validation.valid) {
        message.error(validation.errors.join('; '))
        return
      }
      await fluentAiService.automations.create({
        name: formValues.name,
        description: formValues.description ?? '',
        status: 'draft',
        preset,
      })
      message.success(t('pages.automationCreate.created'))
      navigate('/automations')
    } catch (saveError) {
      message.error(saveError instanceof Error ? saveError.message : String(saveError))
    } finally {
      setSaving(false)
    }
  }

  const renderControl = (entry: SettingCatalogEntry) => {
    const disabled = !included[entry.setting_id]
    const value = values[entry.setting_id]

    if (entry.value_type === 'bool') {
      return (
        <Switch
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(checked) =>
            setValues((current) => ({ ...current, [entry.setting_id]: checked }))
          }
        />
      )
    }
    if (entry.value_type === 'enum') {
      return (
        <Select
          value={value}
          disabled={disabled}
          className="fluent-setting-control"
          options={(entry.allowed_values ?? []).map((option) => ({
            value: option,
            label: formatOption(option),
          }))}
          onChange={(next) => setValues((current) => ({ ...current, [entry.setting_id]: next }))}
        />
      )
    }
    if (entry.value_type === 'int' || entry.value_type === 'float') {
      return (
        <InputNumber
          value={typeof value === 'number' ? value : null}
          disabled={disabled}
          className="fluent-setting-control"
          min={entry.minimum ?? undefined}
          max={entry.maximum ?? undefined}
          step={entry.value_type === 'int' ? 1 : 0.0001}
          precision={entry.value_type === 'int' ? 0 : undefined}
          onChange={(next) =>
            setValues((current) => ({
              ...current,
              [entry.setting_id]: next ?? 0,
            }))
          }
        />
      )
    }
    return (
      <Input
        value={typeof value === 'string' ? value : ''}
        disabled={disabled}
        className="fluent-setting-control"
        onChange={(event) =>
          setValues((current) => ({
            ...current,
            [entry.setting_id]: event.target.value,
          }))
        }
      />
    )
  }

  if (sidecarState === 'error') {
    return (
      <PageContent
        title={t('pages.automationCreate.title')}
        description={t('pages.automationCreate.description')}
      >
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={t('errors.sidecarErrorDescription')}
          retryLabel={t('common.reload')}
          onRetry={() => void loadCatalog()}
        />
      </PageContent>
    )
  }

  if (loading) {
    return (
      <PageContent
        title={t('pages.automationCreate.title')}
        description={t('pages.automationCreate.description')}
      >
        <LoadingState />
      </PageContent>
    )
  }

  if (error) {
    return (
      <PageContent
        title={t('pages.automationCreate.title')}
        description={t('pages.automationCreate.description')}
      >
        <ErrorState
          title={t('errors.sidecarErrorTitle')}
          description={error}
          retryLabel={t('common.reload')}
          onRetry={() => void loadCatalog()}
        />
      </PageContent>
    )
  }

  const tabItems = groups.map((group) => ({
    key: group.key,
    label: (
      <Space>
        {group.icon}
        {group.label}
      </Space>
    ),
    children: (
      <Space direction="vertical" size={14} className="full-width">
        {catalog
          .filter((entry) => entry.group === group.key)
          .map((entry) => (
            <div
              key={entry.setting_id}
              className={`fluent-setting-row ${included[entry.setting_id] ? 'is-included' : ''}`}
            >
              <Checkbox
                checked={Boolean(included[entry.setting_id])}
                onChange={(event) =>
                  setIncluded((current) => ({
                    ...current,
                    [entry.setting_id]: event.target.checked,
                  }))
                }
              >
                <Space direction="vertical" size={2}>
                  <Typography.Text strong>{entry.display_name}</Typography.Text>
                  <Typography.Text type="secondary" className="fluent-setting-description">
                    {entry.description || entry.setting_id}
                  </Typography.Text>
                </Space>
              </Checkbox>
              <div className="fluent-setting-value">{renderControl(entry)}</div>
            </div>
          ))}
      </Space>
    ),
  }))

  return (
    <PageContent
      title={t('pages.automationCreate.title')}
      description={t('pages.automationCreate.description')}
      actions={
        <Tag color="blue">
          {t('pages.automationCreate.selectedSettings', { count: includedCount })}
        </Tag>
      }
    >
      <Card>
        <Form<AutomationFormValues>
          form={form}
          layout="vertical"
          initialValues={{ name: '', description: '' }}
          onFinish={(formValues) => void saveAutomation(formValues)}
        >
          <Form.Item
            name="name"
            label={t('pages.automationCreate.name')}
            rules={[{ required: true, message: t('pages.automationCreate.name') }]}
          >
            <Input maxLength={120} />
          </Form.Item>
          <Form.Item name="description" label={t('pages.automationCreate.descriptionField')}>
            <Input.TextArea rows={2} maxLength={2_000} />
          </Form.Item>

          <Typography.Title level={5}>
            {t('pages.automationCreate.fluentWorkflow')}
          </Typography.Title>
          <Tabs tabPosition="left" items={tabItems} className="fluent-workflow-tabs" />

          <Form.Item className="form-actions">
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>
              {saving
                ? t('pages.automationCreate.saving')
                : t('pages.automationCreate.saveAutomation')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </PageContent>
  )
}
