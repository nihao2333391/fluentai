import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  LockOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { App, Button, Card, Flex, List, Radio, Space, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { CredentialStatus, DatabaseBackupInfo } from '../../../shared/contracts'
import { FluentConnectionCard } from '../components/FluentConnectionCard'
import { MeshingConnectionCard } from '../components/MeshingConnectionCard'
import { PageContent } from '../components/PageState'
import type { AppLanguage } from '../i18n'
import { localizedRuntimeMessage } from '../i18n/runtimeMessages'
import { fluentAiService } from '../services/fluentAi'
import { useAppStore, type ThemeMode } from '../store/appStore'

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
      </Flex>
    </PageContent>
  )
}
