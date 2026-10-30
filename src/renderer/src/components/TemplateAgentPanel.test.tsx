import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import type { AgentModelConfig, AgentRunEvent, FluentAIApi } from '../../../shared/contracts'
import { TemplateAgentPanel } from './TemplateAgentPanel'

const config: AgentModelConfig = {
  display_name: '工程模型',
  model_id: 'test-model',
  base_url: 'https://example.com/v1',
  timeout_seconds: 90,
  enabled: true,
  connection_status: 'passed',
  tool_status: 'passed',
  vision_status: 'untested',
  streaming_status: 'passed',
}

afterEach(() => {
  vi.restoreAllMocks()
  Reflect.deleteProperty(window, 'fluentAI')
})

describe('TemplateAgentPanel', () => {
  it('loads the template session and renders streamed Agent content', async () => {
    let onAgentEvent: ((event: { requestId: string; payload: AgentRunEvent }) => void) | null = null
    const agent = {
      getModelConfig: vi.fn().mockResolvedValue(config),
      saveModelConfig: vi.fn(),
      testModel: vi.fn(),
      testCapabilities: vi.fn(),
      getSession: vi.fn().mockResolvedValue({
        template_id: 7,
        agent_id: 'fluent-template-7',
        session_id: 'fluent-template-session-7',
        messages: [
          {
            id: 'history-1',
            role: 'assistant' as const,
            content: '已恢复模板会话。',
            run_id: null,
            status: 'completed',
            created_at: '2026-10-30T00:00:00Z',
          },
        ],
        needs_range_confirmation: false,
        proactive_suggestions: [],
      }),
      getProactiveSuggestion: vi.fn().mockResolvedValue(null),
      sendMessage: vi.fn().mockResolvedValue('request-1'),
      onEvent: vi.fn((listener) => {
        onAgentEvent = listener
        return () => undefined
      }),
      stopMessage: vi.fn(),
    }
    Object.defineProperty(window, 'fluentAI', {
      configurable: true,
      value: { agent } as unknown as FluentAIApi,
    })

    render(
      <MemoryRouter>
        <TemplateAgentPanel templateId={7} activeStep="add_boundary_layer" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('已恢复模板会话。')).toBeTruthy()
    expect(screen.queryByText('边界层步骤可咨询 Agent，比对两种方法并计算初步参数。')).toBeNull()
    expect(
      screen.queryByText(
        '我可以比较 Uniform 和 Smooth Transition，并根据你提供的工程条件推荐边界层参数。',
      ),
    ).toBeNull()

    fireEvent.change(screen.getByPlaceholderText('描述模型、工况或你想了解的问题…'), {
      target: { value: '请比较 Uniform 和 Smooth。' },
    })
    fireEvent.click(screen.getByRole('button', { name: /发送/ }))
    await waitFor(() =>
      expect(agent.sendMessage).toHaveBeenCalledWith(7, '请比较 Uniform 和 Smooth。', false),
    )
    await waitFor(() => expect(onAgentEvent).not.toBeNull())

    act(() => {
      onAgentEvent?.({ requestId: 'request-1', payload: { type: 'started', run_id: 'run-1' } })
      onAgentEvent?.({
        requestId: 'request-1',
        payload: { type: 'content', run_id: 'run-1', content: '建议先检查特征速度。' },
      })
    })
    expect(await screen.findByText('建议先检查特征速度。')).toBeTruthy()
  })

  it('renders only the generated suggestion with its source and execution trace', async () => {
    const agent = {
      getModelConfig: vi.fn().mockResolvedValue(config),
      getSession: vi.fn().mockResolvedValue({
        template_id: 7,
        agent_id: 'fluent-template-7',
        session_id: 'fluent-template-session-7',
        messages: [],
        needs_range_confirmation: false,
        proactive_suggestions: [],
      }),
      getProactiveSuggestion: vi.fn().mockResolvedValue({
        should_suggest: true,
        relevance_reason: '检索章节讨论当前阶段涉及的增长率输入。',
        suggestion: '检索结果提示本模板阶段需要确认增长率。',
        follow_up_questions: ['当前增长率是多少？'],
        sources: [{ source: '规则.md', section: '增长条件' }],
        run_id: 'proactive-run-1',
        stage_key: 'add_boundary_layer',
        execution_records: [
          {
            tool_name: 'search_boundary_layer_rules',
            status: 'completed',
            target: { query: '当前阶段增长率' },
            result: { results: [{ source: '规则.md', section: '增长条件' }] },
          },
        ],
        created_at: '2026-10-30T00:00:00Z',
      }),
      sendMessage: vi.fn().mockResolvedValue('request-follow-up'),
      onEvent: vi.fn(() => () => undefined),
      stopMessage: vi.fn(),
    }
    Object.defineProperty(window, 'fluentAI', {
      configurable: true,
      value: { agent } as unknown as FluentAIApi,
    })

    render(
      <MemoryRouter>
        <TemplateAgentPanel templateId={7} activeStep="add_boundary_layer" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('检索结果提示本模板阶段需要确认增长率。')).toBeTruthy()
    expect(screen.getByText('来源：规则.md · 增长条件')).toBeTruthy()
    fireEvent.click(screen.getByText('检索与判断记录（1）'))
    expect(await screen.findByText('规则库检索')).toBeTruthy()
    expect(screen.getByText(/命中 1 条规则（规则\.md）/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '当前增长率是多少？' }))
    await waitFor(() =>
      expect(agent.sendMessage).toHaveBeenCalledWith(7, '当前增长率是多少？', false),
    )
  })

  it('passes an uploaded image directly with the user message', async () => {
    const agent = {
      getModelConfig: vi.fn().mockResolvedValue(config),
      getSession: vi.fn().mockResolvedValue({
        template_id: 7,
        agent_id: 'fluent-template-7',
        session_id: 'fluent-template-session-7',
        messages: [],
        needs_range_confirmation: false,
        proactive_suggestions: [],
      }),
      getProactiveSuggestion: vi.fn().mockResolvedValue(null),
      sendMessage: vi.fn().mockResolvedValue('request-image'),
      onEvent: vi.fn(() => () => undefined),
      stopMessage: vi.fn(),
    }
    Object.defineProperty(window, 'fluentAI', {
      configurable: true,
      value: { agent } as unknown as FluentAIApi,
    })

    render(
      <MemoryRouter>
        <TemplateAgentPanel templateId={7} />
      </MemoryRouter>,
    )

    const file = new File(['image-bytes'], 'mesh.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('选择图片附件'), { target: { files: [file] } })
    expect(await screen.findByAltText('mesh.png')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() =>
      expect(agent.sendMessage).toHaveBeenCalledWith(7, '请直接查看并分析我附上的图片。', false, [
        expect.objectContaining({ filename: 'mesh.png', mime_type: 'image/png' }),
      ]),
    )
  })
})
