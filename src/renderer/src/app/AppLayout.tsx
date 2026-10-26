import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  DatabaseOutlined,
  PartitionOutlined,
} from '@ant-design/icons'
import { Alert, Button, Flex, Layout, Menu, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { PermissionState } from '../components/PageState'
import { SidecarStatusBadge } from '../components/SidecarStatusBadge'
import { TaskStatusSurface } from '../components/TaskStatusSurface'
import { useSidecarStore } from '../store/sidecarStore'

const { Header, Sider, Content } = Layout

export function AppLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const sidecarStatus = useSidecarStore((state) => state.status)

  const menuItems = useMemo(
    () => [
      {
        key: 'workspace',
        type: 'group' as const,
        label: t('nav.workspace'),
        children: [
          {
            key: '/meshing',
            icon: <PartitionOutlined />,
            label: t('nav.meshingAutomations'),
          },
          {
            key: '/models',
            icon: <DatabaseOutlined />,
            label: t('nav.myModels'),
          },
        ],
      },
      {
        key: 'system',
        type: 'group' as const,
        label: t('nav.system'),
        children: [
          {
            key: '/settings',
            icon: <SettingOutlined />,
            label: t('nav.settings'),
          },
        ],
      },
    ],
    [t],
  )

  const selectedKey = location.pathname.startsWith('/models')
    ? '/models'
    : location.pathname.startsWith('/meshing')
      ? '/meshing'
      : '/settings'

  return (
    <Layout className="app-layout">
      <Sider
        width={252}
        collapsedWidth={76}
        collapsible
        collapsed={collapsed}
        trigger={null}
        breakpoint="lg"
        onBreakpoint={setCollapsed}
        className="app-sider"
      >
        <div className="brand-block">
          <div className="brand-mark">FA</div>
          {!collapsed ? (
            <div>
              <Typography.Text strong className="brand-name">
                Fluent AI
              </Typography.Text>
              <Typography.Text type="secondary" className="brand-subtitle">
                {t('nav.brandSubtitle')}
              </Typography.Text>
            </div>
          ) : null}
        </div>
        <Menu
          mode="inline"
          items={menuItems}
          selectedKeys={[selectedKey]}
          onClick={({ key }) => navigate(key)}
          className="app-menu"
        />
      </Sider>

      <Layout>
        <Header className="app-header">
          <Flex align="center" gap={12}>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
              aria-label={t('nav.toggleNavigation')}
            />
            <div>
              <Typography.Text strong className="header-title">
                {t('common.appName')}
              </Typography.Text>
              <Typography.Text type="secondary" className="header-path">
                {location.pathname}
              </Typography.Text>
            </div>
          </Flex>
          <Flex align="center" gap={10} wrap>
            <TaskStatusSurface />
            <SidecarStatusBadge />
          </Flex>
        </Header>

        <Content className="app-content">
          {sidecarStatus.state === 'error' ? (
            <Alert
              type="error"
              showIcon
              className="global-alert"
              message={t('errors.sidecarErrorTitle')}
              description={sidecarStatus.message ?? t('errors.sidecarErrorDescription')}
            />
          ) : null}
          {window.fluentAI ? (
            <Outlet />
          ) : (
            <PermissionState
              title={t('errors.bridgeUnavailableTitle')}
              description={t('errors.bridgeUnavailableDescription')}
            />
          )}
        </Content>
      </Layout>
    </Layout>
  )
}
