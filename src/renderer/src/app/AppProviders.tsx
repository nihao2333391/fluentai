import { App as AntdApp, ConfigProvider } from 'antd'
import enUS from 'antd/locale/en_US'
import zhCN from 'antd/locale/zh_CN'
import { useEffect, type ReactNode } from 'react'

import { systemLanguage } from '../i18n'
import { useAppStore } from '../store/appStore'
import { useSidecarStore } from '../store/sidecarStore'
import { getThemeConfig } from '../theme/theme'
import { useSystemDark } from '../theme/useSystemDark'

export function AppProviders({ children }: { children: ReactNode }) {
  const themeMode = useAppStore((state) => state.themeMode)
  const setSidecarStatus = useSidecarStore((state) => state.setStatus)
  const systemDark = useSystemDark()
  const isDark = themeMode === 'dark' || (themeMode === 'system' && systemDark)

  useEffect(() => {
    document.documentElement.lang = systemLanguage === 'zh' ? 'zh-CN' : 'en'
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
  }, [isDark])

  useEffect(() => {
    const sidecar = window.fluentAI?.sidecar
    if (!sidecar) {
      setSidecarStatus({
        state: 'error',
        message: 'Electron preload API is unavailable.',
      })
      return
    }

    let active = true
    void sidecar.getStatus().then((status) => {
      if (active) {
        setSidecarStatus(status)
      }
    })
    const unsubscribe = sidecar.onStatusChanged((status) => {
      if (active) {
        setSidecarStatus(status)
      }
    })
    return () => {
      active = false
      unsubscribe()
    }
  }, [setSidecarStatus])

  return (
    <ConfigProvider
      locale={systemLanguage === 'zh' ? zhCN : enUS}
      theme={getThemeConfig(isDark)}
      componentSize="middle"
    >
      <AntdApp>{children}</AntdApp>
    </ConfigProvider>
  )
}
