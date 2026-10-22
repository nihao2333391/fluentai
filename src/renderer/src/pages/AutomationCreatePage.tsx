import { MinusCircleOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Select, Space, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type {
  PresetDocument,
  PresetItem,
  PresetValue,
  SettingCatalogEntry,
} from '../../../shared/contracts'
import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

interface PresetRow {
  setting_id: string
  value: string
}

interface AutomationFormValues {
  name: string
  description: string
  items: PresetRow[]
}

const parseValue = (entry: SettingCatalogEntry, raw: string): PresetValue => {
  const value = raw.trim()
  switch (entry.value_type) {
    case 'int': {
      const parsed = Number.parseInt(value, 10)
      if (!Number.isInteger(parsed)) throw new Error(`${entry.display_name} requires an integer.`)
      return parsed
    }
    case 'float': {
      const parsed = Number(value)
      if (!Number.isFinite(parsed)) throw new Error(`${entry.display_name} requires a number.`)
      return parsed
    }
    case 'bool':
      if (value !== 'true' && value !== 'false') {
        throw new Error(`${entry.display_name} requires true or false.`)
      }
      return value === 'true'
    default:
      return value
  }
}

export function AutomationCreatePage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<AutomationFormValues>()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [catalog, setCatalog] = useState<SettingCatalogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchCatalog = (): Promise<SettingCatalogEntry[]> => fluentAiService.fluent.catalog()

  const loadCatalog = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      setCatalog(await fetchCatalog())
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
    void fetchCatalog()
      .then((entries) => {
        if (active) setCatalog(entries)
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

  const saveAutomation = async (values: AutomationFormValues): Promise<void> => {
    setSaving(true)
    try {
      const definitions = new Map(catalog.map((entry) => [entry.setting_id, entry]))
      const items: PresetItem[] = values.items.map((row) => {
        const entry = definitions.get(row.setting_id)
        if (!entry) throw new Error(`Unknown setting: ${row.setting_id}`)
        return {
          setting_id: row.setting_id,
          type: entry.value_type,
          value: parseValue(entry, row.value),
          required: true,
        }
      })
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
        name: values.name,
        description: values.description ?? '',
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

  const settingOptions = catalog.map((entry) => ({
    value: entry.setting_id,
    label: `${entry.display_name} (${entry.setting_id})`,
  }))

  return (
    <PageContent
      title={t('pages.automationCreate.title')}
      description={t('pages.automationCreate.description')}
    >
      <Card>
        <Form<AutomationFormValues>
          form={form}
          layout="vertical"
          initialValues={{
            name: '',
            description: '',
            items: [{ setting_id: catalog[0]?.setting_id ?? '', value: '0.001' }],
          }}
          onFinish={(values) => void saveAutomation(values)}
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

          <Typography.Title level={5}>{t('pages.automationCreate.settings')}</Typography.Title>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <Space direction="vertical" size={12} className="full-width">
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" className="preset-row" wrap>
                    <Form.Item
                      name={[field.name, 'setting_id']}
                      rules={[{ required: true }]}
                      className="preset-setting"
                    >
                      <Select options={settingOptions} showSearch optionFilterProp="label" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'value']}
                      rules={[{ required: true }]}
                      className="preset-value"
                    >
                      <Input placeholder={t('pages.automationCreate.value')} />
                    </Form.Item>
                    <Button
                      danger
                      type="text"
                      icon={<MinusCircleOutlined />}
                      onClick={() => remove(field.name)}
                      disabled={fields.length === 1}
                      aria-label={t('common.delete')}
                    />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      setting_id: catalog[0]?.setting_id ?? '',
                      value: '0.001',
                    })
                  }
                >
                  {t('pages.automationCreate.addSetting')}
                </Button>
              </Space>
            )}
          </Form.List>

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
