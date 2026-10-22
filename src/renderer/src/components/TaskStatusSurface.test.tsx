import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { TaskStatusSurface } from './TaskStatusSurface'

const runningJob = {
  id: 'job-1',
  job_type: 'apply-automation',
  status: 'running',
  progress: 55,
  message: 'Model loaded.',
  payload: {},
  result: null,
  error: null,
  created_at: 'now',
  updated_at: 'now',
  started_at: 'now',
  finished_at: null,
}

describe('TaskStatusSurface', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const cancel = vi.fn().mockResolvedValue({
      ...runningJob,
      status: 'cancelled',
      message: 'Cancelled by user.',
    })
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({ state: 'ready' }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      jobs: {
        list: vi.fn().mockResolvedValue([runningJob]),
        get: vi.fn(),
        cancel,
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('shows job progress and cancels a running job', async () => {
    render(
      <AppProviders>
        <TaskStatusSurface />
      </AppProviders>,
    )

    expect(await screen.findByText('1 个活动任务')).toBeInTheDocument()
    fireEvent.click(screen.getByText('1 个活动任务'))
    expect(await screen.findByText('apply-automation')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '取消任务' }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).jobs.cancel).toHaveBeenCalledWith('job-1')
    })
    expect(await screen.findByText('任务已取消')).toBeInTheDocument()
  })
})
