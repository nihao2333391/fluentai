import { Button, Empty, Result, Skeleton, Typography } from 'antd'
import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description: string
  actions?: ReactNode
  children?: ReactNode
}

export function PageContent({ title, description, actions, children }: PageHeaderProps) {
  return (
    <section className="module-page">
      <div className="module-page-heading">
        <div>
          <Typography.Title level={2}>{title}</Typography.Title>
          <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
        </div>
        {actions ? <div className="module-page-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}

interface EmptyStateProps {
  title: string
  description: string
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="page-state-card">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <div>
            <Typography.Text strong>{title}</Typography.Text>
            <Typography.Paragraph type="secondary" className="state-description">
              {description}
            </Typography.Paragraph>
          </div>
        }
      />
    </div>
  )
}

export function LoadingState() {
  return (
    <div className="page-state-card">
      <Skeleton active paragraph={{ rows: 3 }} />
    </div>
  )
}

interface ErrorStateProps {
  title: string
  description: string
  onRetry?: () => void
  retryLabel: string
}

export function ErrorState({ title, description, onRetry, retryLabel }: ErrorStateProps) {
  return (
    <Result
      status="warning"
      title={title}
      subTitle={description}
      extra={
        onRetry ? (
          <Button type="primary" onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : null
      }
    />
  )
}

interface PermissionStateProps {
  title: string
  description: string
}

export function PermissionState({ title, description }: PermissionStateProps) {
  return <Result status="403" title={title} subTitle={description} />
}
