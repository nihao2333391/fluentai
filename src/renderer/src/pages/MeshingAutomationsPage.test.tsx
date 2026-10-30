import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FluentAIApi } from '../../../shared/contracts'
import { AppProviders } from '../app/AppProviders'
import { useSidecarStore } from '../store/sidecarStore'
import { MeshingAutomationsPage } from './MeshingAutomationsPage'

const automation = {
  id: 11,
  name: 'Venturi Meshing',
  description: 'Reference preset',
  model_family: 'Venturi',
  reference_model_id: 21,
  preset: {
    schema_version: 1,
    fluent_version: '25.2.0',
    workflow_type: 'watertight',
    items: [],
  },
  status: 'active',
  category_id: 'venturi',
  revision: 1,
  published_revision: 1,
  created_at: 'now',
  updated_at: 'now',
}

const model = {
  id: 21,
  name: 'venturi.dsco.pmdb',
  file_path: 'D:\\models\\venturi.dsco.pmdb',
  file_size: 100,
  file_mtime: 'now',
  description: '',
  tags: [],
  automation_ids: [],
  default_automation_id: null,
  created_at: 'now',
  updated_at: 'now',
}

const task = {
  id: 'task-1',
  automation_id: 11,
  automation_name: 'Venturi Meshing',
  template_revision: 1,
  model_names: ['venturi.dsco.pmdb'],
  session_id: 'session-1',
  status: 'waiting_surface',
  surface_mesh_status: 'ready',
  volume_mesh_status: 'pending',
  phase: 'surface_ready',
  message: '面网格设置已就绪',
  created_at: 'now',
  updated_at: 'now',
  completed_at: null,
  deleted_at: null,
  artifact_count: 1,
}

const taskHistory = {
  task,
  artifacts: [{
    id: 'artifact-1',
    task_id: task.id,
    archive_id: 'archive-1',
    kind: 'mesh',
    file_path: 'D:\\results\\mesh.msh.h5',
    file_size: 100,
    status: 'retained',
    created_at: 'now',
    metadata: {},
  }],
  events: [{
    id: 'event-1',
    task_id: task.id,
    event_type: 'state_changed',
    status: task.status,
    phase: task.phase,
    message: '已准备好面网格',
    payload: {},
    created_at: 'now',
  }],
}

const LocationProbe = () => {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

describe('MeshingAutomationsPage', () => {
  beforeEach(() => {
    useSidecarStore.setState({
      status: { state: 'ready', message: 'ready', version: '0.1.0', pid: 1, port: 5000 },
    })
    const start = vi.fn().mockResolvedValue({
      session_id: 'session-1',
      task_id: 'task-1',
      automation_id: 11,
      automation_name: automation.name,
      workflow_type: 'watertight',
      status: 'waiting',
      connection: null,
      models: [],
      current_model_index: 0,
      current_step_index: 1,
      steps: [],
      logs: [],
      message: '',
    })
    const categoryRows = [
      { id: 'venturi', name: '文丘里', description: '', is_system: false, template_count: 1, created_at: 'now', updated_at: 'now' },
      { id: 'long-name', name: '汽轮机叶片前缘复杂曲面组件', description: '', is_system: false, template_count: 12, created_at: 'now', updated_at: 'now' },
      { id: 'empty-category', name: '空目录', description: '', is_system: false, template_count: 0, created_at: 'now', updated_at: 'now' },
    ]
    const api = {
      sidecar: {
        getStatus: vi.fn().mockResolvedValue({ state: 'ready' }),
        restart: vi.fn(),
        onStatusChanged: vi.fn(() => () => undefined),
      },
      models: { list: vi.fn().mockResolvedValue([model]) },
      meshingAutomations: {
        list: vi.fn().mockResolvedValue([automation]),
        delete: vi.fn().mockImplementation(async (id: string) => {
          const index = categoryRows.findIndex((item) => item.id === id)
          if (index >= 0) categoryRows.splice(index, 1)
        }),
      },
      categories: {
        list: vi.fn().mockImplementation(async () => categoryRows),
        create: vi.fn().mockImplementation(async ({ name }: { name: string }) => {
          const created = { id: 'new-category', name, description: '', is_system: false, template_count: 0, created_at: 'now', updated_at: 'now' }
          categoryRows.push(created)
          return created
        }),
        rename: vi.fn().mockImplementation(async (id: string, name: string) => {
          const category = categoryRows.find((item) => item.id === id)
          if (!category) throw new Error('目录不存在')
          category.name = name
          category.updated_at = 'renamed'
          return { ...category }
        }),
        delete: vi.fn(),
      },
      meshingTasks: {
        list: vi.fn().mockResolvedValue([task]),
        history: vi.fn().mockResolvedValue(taskHistory),
        delete: vi.fn().mockResolvedValue({ task_id: task.id, deleted: true }),
      },
      meshingLive: { start },
    } as unknown as FluentAIApi
    Object.defineProperty(window, 'fluentAI', { configurable: true, value: api })
  })

  it('starts a live Meshing session with the selected geometry model', async () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <MeshingAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findAllByText('Venturi Meshing')).not.toHaveLength(0)
    fireEvent.click(await screen.findByRole('button', { name: '应用' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.mouseDown(within(dialog).getByRole('combobox'))
    fireEvent.click(await screen.findByText(/venturi\.dsco\.pmdb — D:\\models\\venturi\.dsco\.pmdb/))
    fireEvent.click(within(dialog).getByRole('button', { name: /应\s*用/ }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).meshingLive.start).toHaveBeenCalledWith({
        automation_id: 11,
        model_ids: [21],
        connection: null,
      })
    })
  })

  it('opens the existing Meshing preset in the editor', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing']}>
          <MeshingAutomationsPage />
          <LocationProbe />
        </MemoryRouter>
      </AppProviders>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '编辑' }))

    expect(screen.getByTestId('location')).toHaveTextContent('/meshing/11/edit')
  })

  it('shows durable tasks and the two mesh progress nodes', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing']}>
          <MeshingAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByText('任务进程')).toBeInTheDocument()
    expect(screen.getByText('等待面网格')).toBeInTheDocument()
    expect(screen.getByText('面网格')).toBeInTheDocument()
    expect(screen.getByText('体网格')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '进入任务' })).toBeInTheDocument()
  })

  it('opens persisted artifact and event history for a task', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing']}>
          <MeshingAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '查看记录' }))

    expect(await screen.findByText('任务历史与产物')).toBeInTheDocument()
    expect(screen.getByText(/mesh\.msh\.h5/)).toBeInTheDocument()
    expect(screen.getByText(/已准备好面网格/)).toBeInTheDocument()
    expect((window.fluentAI as FluentAIApi).meshingTasks.history).toHaveBeenCalledWith(
      task.id,
      false,
    )
  })

  it('allows typing a directory name and creates it from the current folder', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing']}>
          <MeshingAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '新建目录' }))
    const dialog = await screen.findByRole('dialog')
    const nameInput = within(dialog).getByPlaceholderText('输入目录名称')
    fireEvent.change(nameInput, { target: { value: '测试零件' } })
    expect(nameInput).toHaveValue('测试零件')
    fireEvent.click(within(dialog).getByRole('button', { name: '创建目录' }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).categories.create).toHaveBeenCalledWith({
        name: '测试零件',
        description: '',
      })
    })
  })

  it('renames a directory while keeping templates and count badges in place', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/meshing']}>
          <MeshingAutomationsPage />
        </MemoryRouter>
      </AppProviders>,
    )

    expect(await screen.findByRole('heading', { name: '文丘里' })).toBeInTheDocument()
    const countBadges = document.querySelectorAll('.template-directory-count')
    expect(Array.from(countBadges).map((badge) => badge.textContent)).toEqual(['1', '12', '0'])
    expect(countBadges).toHaveLength(3)
    expect(screen.getByRole('button', { name: '编辑目录' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('button', { name: '重命名目录 文丘里' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '编辑目录' }))
    expect(screen.getByRole('button', { name: '重命名目录 文丘里' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除目录 汽轮机叶片前缘复杂曲面组件' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '重命名目录 文丘里' }))
    const dialog = await screen.findByRole('dialog')
    const nameInput = within(dialog).getByRole('textbox', { name: '目录名称' })
    expect(nameInput).toHaveValue('文丘里')
    fireEvent.change(nameInput, { target: { value: '文丘里管' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '保存名称' }))

    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).categories.rename).toHaveBeenCalledWith(
        'venturi',
        '文丘里管',
      )
    })
    expect(await screen.findByRole('heading', { name: '文丘里管' })).toBeInTheDocument()
    expect(screen.getAllByText('Venturi Meshing')).not.toHaveLength(0)
    expect(Array.from(document.querySelectorAll('.template-directory-count')).map((badge) => badge.textContent)).toEqual(['1', '12', '0'])

    fireEvent.click(screen.getByRole('button', { name: '删除目录 空目录' }))
    const deleteDialog = await screen.findByRole('dialog')
    expect(within(deleteDialog).getByText('此目录为空。删除后无法恢复。')).toBeInTheDocument()
    fireEvent.click(within(deleteDialog).getByRole('button', { name: '删除目录' }))
    await waitFor(() => {
      expect((window.fluentAI as FluentAIApi).categories.delete).toHaveBeenCalledWith('empty-category')
    })
    expect(screen.queryByRole('button', { name: 'folder 空目录 0' })).not.toBeInTheDocument()
    expect(Array.from(document.querySelectorAll('.template-directory-count')).map((badge) => badge.textContent)).toEqual(['1', '12'])
  })
})
