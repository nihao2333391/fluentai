import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  LockOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Flex,
  Form,
  Input,
  InputNumber,
  List,
  Radio,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type {
  AgentModelConfig,
  AgentModelTestRequest,
  CredentialStatus,
  DatabaseBackupInfo,
} from '../../../shared/contracts'
import { FluentConnectionCard } from '../components/FluentConnectionCard'
import { MeshingConnectionCard } from '../components/MeshingConnectionCard'
import { PageContent } from '../components/PageState'
import type { AppLanguage } from '../i18n'
import { localizedRuntimeMessage } from '../i18n/runtimeMessages'
import { fluentAiService } from '../services/fluentAi'
import { useAppStore, type ThemeMode } from '../store/appStore'

const toAgentModelTestRequest = (config: AgentModelConfig): AgentModelTestRequest => ({
  display_name: config.display_name,
  model_id: config.model_id,
  base_url: config.base_url,
  timeout_seconds: config.timeout_seconds,
})

export function SettingsPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const themeMode = useAppStore((state) => state.themeMode)
  const language = useAppStore((state) => state.language)
  const setThemeMode = useAppStore((state) => state.setThemeMode)
  const setLanguage = useAppStore((state) => state.setLanguage)
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null)
  const [backups, setBackups] = useState<DatabaseBackupInfo[]>([])
  const [backupBusy, setBackupBusy] = useState(false)
  const [agentForm] = Form.useForm<AgentModelTestRequest>()
  const [agentConfig, setAgentConfig] = useState<AgentModelConfig | null>(null)
  const [agentCredentialStatus, setAgentCredentialStatus] = useState<CredentialStatus | null>(null)
  const [agentKey, setAgentKey] = useState('')
  const [agentBusy, setAgentBusy] = useState(false)
  const [agentError, setAgentError] = useState<string | null>(null)

  useEffect(() => {
    if (!window.fluentAI) {
      return
    }
    let active = true
    void window.fluentAI.credentials.getStatus().then((status) => {
      if (active) {
        setCredentialStatus(status)
      }
    })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const api = window.fluentAI
    if (!api) return
    let active = true
    void Promise.all([api.agent.getModelConfig(), api.credentials.getAgentApiKeyStatus()])
      .then(([config, credentialStatus]) => {
        if (!active) return
        setAgentConfig(config)
        setAgentCredentialStatus(credentialStatus)
        agentForm.setFieldsValue({
          display_name: config.display_name,
          model_id: config.model_id,
          base_url: config.base_url,
          timeout_seconds: config.timeout_seconds,
        })
      })
      .catch((error: unknown) => {
        if (active) setAgentError(error instanceof Error ? error.message : String(error))
      })
    return () => {
      active = false
    }
  }, [agentForm])

  const saveAgentConfig = async (enable: boolean): Promise<AgentModelConfig> => {
    const api = window.fluentAI
    if (!api) throw new Error('桌面通信接口暂不可用。')
    const values = await agentForm.validateFields()
    const keyChanged = Boolean(agentKey.trim())
    const changed =
      !agentConfig ||
      agentConfig.model_id !== values.model_id ||
      agentConfig.base_url !== values.base_url ||
      agentConfig.display_name !== values.display_name ||
      agentConfig.timeout_seconds !== values.timeout_seconds ||
      keyChanged
    if (enable && (changed || agentConfig.connection_status !== 'passed')) {
      throw new Error('模型配置或 API Key 已变化，请重新测试连接后再启用。')
    }
    if (keyChanged) {
      const status = await api.credentials.setAgentApiKey(agentKey.trim())
      setAgentCredentialStatus(status)
      setAgentKey('')
    }
    const next: AgentModelConfig = {
      display_name: values.display_name,
      model_id: values.model_id,
      base_url: values.base_url,
      timeout_seconds: values.timeout_seconds,
      enabled: enable || (!changed && agentConfig.enabled),
      connection_status: changed ? 'untested' : agentConfig.connection_status,
      tool_status: changed ? 'untested' : agentConfig.tool_status,
      vision_status: changed ? 'untested' : agentConfig.vision_status,
      streaming_status: changed ? 'untested' : agentConfig.streaming_status,
    }
    const saved = await api.agent.saveModelConfig(next)
    setAgentConfig(saved)
    return saved
  }

  const testAgentModel = async (): Promise<void> => {
    const api = window.fluentAI
    if (!api) return
    setAgentBusy(true)
    setAgentError(null)
    let attemptedConfig: AgentModelConfig | null = null
    try {
      attemptedConfig = await saveAgentConfig(false)
      const result = await api.agent.testModel(toAgentModelTestRequest(attemptedConfig))
      const tested: AgentModelConfig = {
        ...attemptedConfig,
        connection_status: result.status,
        enabled: attemptedConfig.enabled,
      }
      const saved = await api.agent.saveModelConfig(tested)
      setAgentConfig(saved)
      message.success(`文本连接测试通过：${result.message}`)
    } catch (error) {
      const failed = attemptedConfig
        ? { ...attemptedConfig, connection_status: 'failed' as const, enabled: false }
        : null
      if (failed) {
        setAgentConfig(await api.agent.saveModelConfig(failed))
      }
      setAgentError(error instanceof Error ? error.message : String(error))
    } finally {
      setAgentBusy(false)
    }
  }

  const testAgentCapabilities = async (): Promise<void> => {
    const api = window.fluentAI
    if (!api) return
    setAgentBusy(true)
    setAgentError(null)
    try {
      const config = await saveAgentConfig(false)
      const result = await api.agent.testCapabilities(toAgentModelTestRequest(config))
      const saved = await api.agent.saveModelConfig({
        ...config,
        tool_status: result.tool_status,
        streaming_status: result.streaming_status,
        vision_status: 'untested',
      })
      setAgentConfig(saved)
      message.info(result.message)
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : String(error))
    } finally {
      setAgentBusy(false)
    }
  }

  const activateAgentModel = async (): Promise<void> => {
    const api = window.fluentAI
    if (!api) return
    setAgentBusy(true)
    setAgentError(null)
    try {
      const saved = await saveAgentConfig(true)
      if (saved.connection_status !== 'passed') {
        throw new Error('请先通过文本连接测试，再启用模型。')
      }
      setAgentConfig(saved)
      message.success('全局 Agent 模型已启用。')
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : String(error))
    } finally {
      setAgentBusy(false)
    }
  }

  const saveAgentSettings = async (): Promise<void> => {
    setAgentBusy(true)
    setAgentError(null)
    try {
      await saveAgentConfig(false)
      message.success('AI 模型配置已保存。')
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : String(error))
    } finally {
      setAgentBusy(false)
    }
  }

  const loadBackups = async (): Promise<void> => {
    const result = await fluentAiService.system.listBackups()
    setBackups(result.backups.slice(0, 5))
  }

  useEffect(() => {
    if (!window.fluentAI) return
    let active = true
    void fluentAiService.system
      .listBackups()
      .then((result) => {
        if (active) setBackups(result.backups.slice(0, 5))
      })
      .catch(() => {
        if (active) setBackups([])
      })
    return () => {
      active = false
    }
  }, [])

  const createBackup = async (): Promise<void> => {
    setBackupBusy(true)
    try {
      const backup = await fluentAiService.system.createBackup()
      message.success(t('settings.backupCreated', { name: backup.name }))
      await loadBackups()
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBackupBusy(false)
    }
  }

  const restoreBackup = (backup: DatabaseBackupInfo): void => {
    modal.confirm({
      title: t('settings.restoreTitle'),
      content: t('settings.restoreDescription', { name: backup.name }),
      okText: t('settings.restore'),
      okButtonProps: { danger: true },
      onOk: async () => {
        setBackupBusy(true)
        try {
          const report = await fluentAiService.system.restoreBackup(backup.name)
          message.success(localizedRuntimeMessage(t, report.message))
          await loadBackups()
        } finally {
          setBackupBusy(false)
        }
      },
    })
  }

  return (
    <PageContent title={t('pages.settings.title')} description={t('pages.settings.description')}>
      <Flex vertical gap={16}>
        <Card title={t('settings.appearance')}>
          <Flex vertical gap={24}>
            <div className="setting-row">
              <div>
                <Typography.Text strong>{t('settings.theme')}</Typography.Text>
                <Typography.Paragraph type="secondary" className="setting-description">
                  {t('settings.themeDescription')}
                </Typography.Paragraph>
              </div>
              <Radio.Group
                optionType="button"
                buttonStyle="solid"
                value={themeMode}
                onChange={(event) => setThemeMode(event.target.value as ThemeMode)}
                options={[
                  { value: 'light', label: t('settings.light') },
                  { value: 'dark', label: t('settings.dark') },
                  { value: 'system', label: t('settings.system') },
                ]}
              />
            </div>
            <div className="setting-row">
              <div>
                <Typography.Text strong>{t('settings.language')}</Typography.Text>
                <Typography.Paragraph type="secondary" className="setting-description">
                  {t('settings.languageDescription')}
                </Typography.Paragraph>
              </div>
              <Radio.Group
                optionType="button"
                buttonStyle="solid"
                value={language}
                onChange={(event) => setLanguage(event.target.value as AppLanguage)}
                options={[
                  { value: 'zh', label: t('settings.chinese') },
                  { value: 'en', label: t('settings.english') },
                ]}
              />
            </div>
          </Flex>
        </Card>

        <FluentConnectionCard />
        <MeshingConnectionCard />

        <Card
          title={t('settings.dataSafety')}
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => void loadBackups()}>
                {t('common.reload')}
              </Button>
              <Button
                type="primary"
                icon={<DatabaseOutlined />}
                loading={backupBusy}
                onClick={() => void createBackup()}
              >
                {t('settings.createBackup')}
              </Button>
            </Space>
          }
        >
          <Typography.Paragraph type="secondary">
            {t('settings.dataSafetyDescription')}
          </Typography.Paragraph>
          <List
            size="small"
            dataSource={backups}
            locale={{ emptyText: t('settings.noBackups') }}
            renderItem={(backup) => (
              <List.Item
                actions={[
                  <Button
                    key="restore"
                    danger
                    type="text"
                    icon={<CloudDownloadOutlined />}
                    disabled={backupBusy}
                    onClick={() => restoreBackup(backup)}
                  >
                    {t('settings.restore')}
                  </Button>,
                ]}
              >
                <Space direction="vertical" size={2}>
                  <Typography.Text strong>{backup.name}</Typography.Text>
                  <Typography.Text type="secondary">
                    {new Date(backup.created_at).toLocaleString()} ·{' '}
                    {(backup.size / 1024).toFixed(1)} KB
                  </Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        </Card>

        <Card title={t('settings.credentials')}>
          <Flex align="center" justify="space-between" gap={24} wrap>
            <Space direction="vertical" size={8}>
              <Tag
                icon={
                  credentialStatus?.encryptionAvailable ? (
                    <CheckCircleOutlined />
                  ) : (
                    <WarningOutlined />
                  )
                }
                color={credentialStatus?.encryptionAvailable ? 'success' : 'warning'}
              >
                {credentialStatus?.encryptionAvailable
                  ? t('settings.credentialAvailable')
                  : t('settings.credentialUnavailable')}
              </Tag>
              <Tag
                icon={<LockOutlined />}
                color={credentialStatus?.configured ? 'processing' : 'default'}
              >
                {credentialStatus?.configured
                  ? t('settings.credentialConfigured')
                  : t('settings.credentialNotConfigured')}
              </Tag>
            </Space>
            <Typography.Text type="secondary" className="stage-note">
              {t('settings.stageNote')}
            </Typography.Text>
          </Flex>
        </Card>

        <Card title="AI 模型配置" extra={<Tag color="blue">所有模板 Agent 共用</Tag>}>
          <Typography.Paragraph type="secondary">
            使用 OpenAI 兼容接口。API Key 由桌面系统加密保存，页面不会回显已保存的 Key。
          </Typography.Paragraph>
          <Form form={agentForm} layout="vertical" initialValues={{ timeout_seconds: 90 }}>
            <Flex gap={16} wrap>
              <Form.Item
                name="display_name"
                label="模型显示名称"
                rules={[{ required: true, message: '请填写模型显示名称。' }]}
                style={{ flex: '1 1 220px' }}
              >
                <Input maxLength={120} placeholder="例如：工程辅助模型" />
              </Form.Item>
              <Form.Item
                name="model_id"
                label="Model ID"
                rules={[{ required: true, message: '请填写供应商提供的 Model ID。' }]}
                style={{ flex: '1 1 220px' }}
              >
                <Input maxLength={200} placeholder="供应商提供的模型 ID" />
              </Form.Item>
            </Flex>
            <Form.Item
              name="base_url"
              label="Base URL"
              rules={[
                { required: true, type: 'url', message: '请填写有效的 OpenAI 兼容接口地址。' },
              ]}
            >
              <Input maxLength={500} placeholder="https://api.example.com/v1" />
            </Form.Item>
            <Flex gap={16} wrap>
              <Form.Item label="API Key（留空则保留已保存的 Key）" style={{ flex: '1 1 320px' }}>
                <Input.Password
                  autoComplete="new-password"
                  value={agentKey}
                  onChange={(event) => setAgentKey(event.target.value)}
                  placeholder={
                    agentCredentialStatus?.configured ? '已加密保存，留空保持不变' : '输入 API Key'
                  }
                />
              </Form.Item>
              <Form.Item name="timeout_seconds" label="请求超时（秒）">
                <InputNumber min={10} max={300} />
              </Form.Item>
            </Flex>
          </Form>
          <Flex gap={8} wrap align="center">
            <Tag color={agentConfig?.enabled ? 'success' : 'default'}>
              {agentConfig?.enabled ? '已启用' : '未启用'}
            </Tag>
            <Tag color={agentConfig?.connection_status === 'passed' ? 'success' : 'default'}>
              文本连接：{agentConfig?.connection_status ?? '未测试'}
            </Tag>
            <Tag>工具调用：{agentConfig?.tool_status ?? '未测试'}</Tag>
            <Tag>图片理解：{agentConfig?.vision_status ?? '未测试'}</Tag>
            <Tag>流式输出：{agentConfig?.streaming_status ?? '未测试'}</Tag>
            <Button loading={agentBusy} onClick={() => void testAgentModel()}>
              测试文本连接
            </Button>
            <Button loading={agentBusy} onClick={() => void saveAgentSettings()}>
              保存配置
            </Button>
            <Button
              loading={agentBusy}
              disabled={
                agentConfig?.connection_status !== 'passed' || !agentCredentialStatus?.configured
              }
              onClick={() => void testAgentCapabilities()}
            >
              检测工具与流式能力
            </Button>
            <Button
              type="primary"
              loading={agentBusy}
              disabled={agentConfig?.connection_status !== 'passed'}
              onClick={() => void activateAgentModel()}
            >
              启用全局模型
            </Button>
          </Flex>
          {agentError ? (
            <Alert style={{ marginTop: 12 }} type="error" showIcon message={agentError} />
          ) : null}
          {agentConfig?.enabled ? (
            <Typography.Text type="secondary">
              当前模型：{agentConfig.display_name} · {agentConfig.model_id}
            </Typography.Text>
          ) : null}
        </Card>
      </Flex>
    </PageContent>
  )
}
