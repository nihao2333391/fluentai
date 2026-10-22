import { ClockCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { App, Button, List, Popover, Progress, Space, Tag, Tooltip, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Job } from '../../../shared/contracts'
import { useSidecarStore } from '../store/sidecarStore'

const statusColor = (status: Job['status']): string => {
  if (status === 'succeeded') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'cancelled') return 'orange'
  if (status === 'running') return 'blue'
  return 'default'
}

export function TaskStatusSurface() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const status = useSidecarStore((state) => state.status)
  const [jobs, setJobs] = useState<Job[]>([])

  useEffect(() => {
    if (status.state !== 'ready' || !window.fluentAI) {
      return
    }

    let active = true
    const refresh = async (): Promise<void> => {
      try {
        const nextJobs = await window.fluentAI!.jobs.list(20)
        if (active) setJobs(nextJobs)
      } catch {
        if (active) setJobs([])
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2_000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [status.state])

  const activeCount = jobs.filter(
    (job) => job.status === 'queued' || job.status === 'running',
  ).length
  const visibleCount = status.state === 'ready' ? activeCount : 0
  const label = visibleCount > 0 ? t('tasks.active', { count: visibleCount }) : t('tasks.none')

  const cancel = async (job: Job): Promise<void> => {
    try {
      const updated = await window.fluentAI!.jobs.cancel(job.id)
      setJobs((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      message.success(t('tasks.cancelled'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    }
  }

  const content = (
    <div className="task-popover">
      <Typography.Text strong>{t('tasks.title')}</Typography.Text>
      {jobs.length === 0 ? (
        <Typography.Paragraph type="secondary" className="task-empty">
          {t('tasks.noJobs')}
        </Typography.Paragraph>
      ) : (
        <List
          size="small"
          dataSource={jobs}
          renderItem={(job) => (
            <List.Item
              actions={
                job.status === 'queued' || job.status === 'running'
                  ? [
                      <Button
                        key="cancel"
                        type="text"
                        danger
                        size="small"
                        icon={<CloseCircleOutlined />}
                        onClick={() => void cancel(job)}
                        aria-label={t('tasks.cancel')}
                      />,
                    ]
                  : undefined
              }
            >
              <Space direction="vertical" size={4} className="full-width">
                <Space wrap>
                  <Tag color={statusColor(job.status)}>{job.status}</Tag>
                  <Typography.Text>{job.job_type}</Typography.Text>
                  <Typography.Text type="secondary">
                    {new Date(job.updated_at).toLocaleTimeString()}
                  </Typography.Text>
                </Space>
                <Typography.Text type="secondary" ellipsis>
                  {job.message || job.error || job.id}
                </Typography.Text>
                <Progress
                  percent={job.progress}
                  size="small"
                  status={job.status === 'failed' ? 'exception' : undefined}
                />
              </Space>
            </List.Item>
          )}
        />
      )}
    </div>
  )

  return (
    <Popover content={content} title={t('tasks.details')} trigger="click" placement="bottomRight">
      <Tooltip title={t('tasks.title')}>
        <Tag icon={<ClockCircleOutlined />} className="task-tag">
          {label}
        </Tag>
      </Tooltip>
    </Popover>
  )
}
