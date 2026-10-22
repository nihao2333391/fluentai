import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  it('shows the ready sidecar and all planned modules', async () => {
    const readyStatus = {
      state: 'ready' as const,
      message: 'FastAPI sidecar is ready.',
      version: '0.1.0',
      pid: 4321,
      port: 61234,
    }
    const restart = vi.fn().mockResolvedValue(readyStatus)

    Object.defineProperty(window, 'fluentAI', {
      configurable: true,
      value: {
        platform: 'win32',
        sidecar: {
          getStatus: vi.fn().mockResolvedValue(readyStatus),
          restart,
          onStatusChanged: vi.fn(() => () => undefined),
        },
      },
    })

    render(<App />)

    expect(await screen.findByText('已就绪')).toBeInTheDocument()
    expect(screen.getByText('PID 4321')).toBeInTheDocument()
    expect(screen.getByText('127.0.0.1:61234')).toBeInTheDocument()
    expect(screen.getByText('自动化创建')).toBeInTheDocument()
    expect(screen.getByText('我的自动化')).toBeInTheDocument()
    expect(screen.getByText('我的模型')).toBeInTheDocument()
    expect(screen.getByText('设置')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重启侧车' }))
    await waitFor(() => expect(restart).toHaveBeenCalledTimes(1))
  })
})
