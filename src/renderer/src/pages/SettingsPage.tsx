import { CheckCircleOutlined, LockOutlined, WarningOutlined } from '@ant-design/icons'
import { Card, Flex, Radio, Select, Space, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { CredentialStatus } from '../../../shared/contracts'
import { PageContent } from '../components/PageState'
import { useAppStore, type Language, type ThemeMode } from '../store/appStore'

export function SettingsPage() {
  const { t } = useTranslation()
  const themeMode = useAppStore((state) => state.themeMode)
  const language = useAppStore((state) => state.language)
  const setThemeMode = useAppStore((state) => state.setThemeMode)
  const setLanguage = useAppStore((state) => state.setLanguage)
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null)

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
              <Select<Language>
                value={language}
                onChange={setLanguage}
                className="language-select"
                options={[
                  { value: 'zh', label: '简体中文' },
                  { value: 'en', label: 'English' },
                ]}
              />
            </div>
          </Flex>
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
