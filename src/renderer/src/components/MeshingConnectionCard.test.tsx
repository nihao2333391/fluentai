import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MeshingConnectionCard } from './MeshingConnectionCard'

describe('MeshingConnectionCard', () => {
  const read = vi.fn()
  const write = vi.fn()

  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    read.mockReset().mockResolvedValue({
      workflow_type: 'watertight',
      status: 'success',
      task_names: ['import_geometry'],
      items: [
        {
          task_path: ['import_geometry'],
          argument_path: ['length_unit'],
          compound_child_name: null,
          found: true,
          value: 'mm',
          error: null,
        },
      ],
      error: null,
    })
    write.mockReset().mockResolvedValue({
      workflow_type: 'watertight',
      status: 'success',
      verified: true,
      results: [
        {
          task_path: ['import_geometry'],
          argument_path: ['length_unit'],
          compound_child_name: null,
          expected: 'mm',
          actual: 'mm',
          success: true,
          message: '',
        },
      ],
      error: null,
    })
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({
          state: 'ready',
          message: 'ready',
          version: '0.1.0',
          pid: 1,
          port: 5000,
        }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      settings: {
        get: vi.fn().mockResolvedValue({ values: {} }),
        update: vi.fn(),
      },
      meshing: {
        status: vi.fn().mockResolvedValue({
          connected: true,
          mode: 'launch',
          version: 'Ansys Fluent 2025 R2',
          pid: 123,
          host: 'localhost',
          port: 5000,
        }),
        connect: vi.fn(),
        disconnect: vi.fn(),
        read,
        write,
      },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('reads current values and verifies a safe writeback', async () => {
    render(
      <AppProviders>
        <MeshingConnectionCard />
      </AppProviders>,
    )

    expect(await screen.findByText('已连接')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /连接与读写诊断/ }))

    await waitFor(() => {
      expect(read).toHaveBeenCalledOnce()
      expect(write).toHaveBeenCalledOnce()
    })
    expect(await screen.findByText('已写入并回读 1 项')).toBeInTheDocument()
  })
})
