import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AgentToolMessage, summarizeToolContent } from './AgentToolMessage'
import { MarkdownText } from './MarkdownText'

describe('MarkdownText', () => {
  it('渲染加粗、行内代码、列表与换行', () => {
    const { container } = render(
      <MarkdownText
        text={'**必需数据：**\n- 密度 `ρ [kg/m³]`\n- 速度 `U [m/s]`\n\n第二段'}
      />,
    )
    expect(container.querySelector('.md-strong')?.textContent).toBe('必需数据：')
    const codes = container.querySelectorAll('.md-code')
    expect(codes).toHaveLength(2)
    const list = container.querySelector('.md-list')
    expect(list?.querySelectorAll('.md-li')).toHaveLength(2)
    const paragraphs = container.querySelectorAll('.md-p')
    expect(paragraphs).toHaveLength(2)
  })

  it('渲染链接且不注入 HTML', () => {
    const { container } = render(
      <MarkdownText text="参考 https://example.com/docs<br>与 <b>恶意</b>" />,
    )
    const link = container.querySelector('a[href="https://example.com/docs"]')
    expect(link).toBeTruthy()
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toContain('<b>恶意</b>')
  })

  it('渲染围栏代码块与引用', () => {
    const { container } = render(
      <MarkdownText text={'> **用途**：估算首层高度\n\n```\nRe = ρUD/μ\n```'} />,
    )
    expect(container.querySelector('.md-quote .md-strong')?.textContent).toBe('用途')
    expect(container.querySelector('.md-pre')?.textContent).toBe('Re = ρUD/μ')
  })
})

describe('AgentToolMessage', () => {
  it('running 状态渲染为一行状态文字', () => {
    render(
      <AgentToolMessage
        toolName="search_boundary_layer_rules"
        toolStatus="running"
        content='{"query": "边界层 层数"}'
      />,
    )
    expect(screen.getByText(/正在规则库检索/)).toBeTruthy()
  })

  it('completed 的检索结果渲染为命中摘要且详情默认收起', () => {
    const result = JSON.stringify({
      status: 'matched',
      query: '边界层',
      results: [{ source: '规则A.md', section: '§1' }],
    })
    const { container } = render(
      <AgentToolMessage
        toolName="search_boundary_layer_rules"
        toolStatus="completed"
        content={result}
      />,
    )
    expect(screen.getByText(/命中 1 条规则（规则A\.md）/)).toBeTruthy()
    expect(container.querySelector('.agent-tool-detail')).toBeNull()
  })

  it('Smooth 层数结果给出关键数值摘要', () => {
    expect(
      summarizeToolContent(
        'calculate_smooth_layers',
        'completed',
        JSON.stringify({
          recommended_layers: 10,
          first_cell_y_plus: 1,
          target_outer_y_plus: 50,
          growth_rate: 1.2,
        }),
      ),
    ).toContain('推荐层数 10 层')
  })

  it('Uniform 超范围结果给出确认提示', () => {
    expect(
      summarizeToolContent(
        'calculate_uniform_first_height',
        'completed',
        JSON.stringify({ confirmation_required: true, reynolds_number: 1200 }),
      ),
    ).toContain('超出估算适用范围')
  })
})
