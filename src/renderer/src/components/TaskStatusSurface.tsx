import { ClockCircleOutlined } from '@ant-design/icons'
import { Tag, Tooltip } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useSidecarStore } from '../store/sidecarStore'

export function TaskStatusSurface() {
  const { t } = useTranslation()
  const status = useSidecarStore((state) => state.status)
  const [activeCount, setActiveCount] = useState(0)

  useEffect(() => {
    if (status.state !== 'ready' || !window.fluentAI) {
      return
    }

    let active = true
    const refresh = async (): Promise<void> => {
      try {
        const jobs = await window.fluentAI!.jobs.list(20)
        if (active) {
          setActiveCount(
            jobs.filter((job) => job.status === 'queued' || job.status === 'running').length,
          )
        }
      } catch {
        if (active) {
          setActiveCount(0)
        }
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2_000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [status.state])

  const visibleCount = status.state === 'ready' ? activeCount : 0
  const label = visibleCount > 0 ? t('tasks.active', { count: visibleCount }) : t('tasks.none')

  return (
    <Tooltip title={t('tasks.title')}>
      <Tag icon={<ClockCircleOutlined />} className="task-tag">
        {label}
      </Tag>
    </Tooltip>
  )
}
