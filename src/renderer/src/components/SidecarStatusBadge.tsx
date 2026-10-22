import { ReloadOutlined } from '@ant-design/icons'
import { Badge, Button, Descriptions, Popover, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useSidecarStore } from '../store/sidecarStore'

const statusColor = {
  stopped: 'default',
  starting: 'processing',
  ready: 'success',
  restarting: 'warning',
  error: 'error',
} as const

export function SidecarStatusBadge() {
  const { t } = useTranslation()
  const status = useSidecarStore((state) => state.status)
  const setStatus = useSidecarStore((state) => state.setStatus)
  const [restarting, setRestarting] = useState(false)

  const restart = async (): Promise<void> => {
    const sidecar = window.fluentAI?.sidecar
    if (!sidecar || restarting) {
      return
    }
    setRestarting(true)
    try {
      setStatus(await sidecar.restart())
    } finally {
      setRestarting(false)
    }
  }

  const label = t(`sidecar.${status.state}`)
  const content = (
    <div className="sidecar-popover">
      <Descriptions column={1} size="small">
        <Descriptions.Item label={t('sidecar.title')}>{label}</Descriptions.Item>
        {status.version ? (
          <Descriptions.Item label="Version">
            {t('sidecar.version', { version: status.version })}
          </Descriptions.Item>
        ) : null}
        {status.pid ? (
          <Descriptions.Item label="PID">{t('sidecar.pid', { pid: status.pid })}</Descriptions.Item>
        ) : null}
        {status.port ? (
          <Descriptions.Item label="Port">
            {t('sidecar.port', { port: status.port })}
          </Descriptions.Item>
        ) : null}
      </Descriptions>
      {status.message ? (
        <Typography.Paragraph type="secondary" className="popover-message">
          {status.message}
        </Typography.Paragraph>
      ) : null}
      <Button
        block
        icon={<ReloadOutlined />}
        loading={restarting}
        onClick={() => void restart()}
        disabled={!window.fluentAI}
      >
        {restarting ? t('sidecar.restartingAction') : t('sidecar.restart')}
      </Button>
    </div>
  )

  return (
    <Popover content={content} title={t('sidecar.title')} trigger="click">
      <Tag color={statusColor[status.state]} className="status-tag">
        <Space size={6}>
          <Badge status={statusColor[status.state]} />
          {t('sidecar.title')} · {label}
        </Space>
      </Tag>
    </Popover>
  )
}
