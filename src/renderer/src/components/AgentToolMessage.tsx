import { Collapse, Typography } from 'antd'

/**
 * Agent 工具调用消息的紧凑渲染：
 * - running：一行细状态文字（完成后由上层过滤隐藏）
 * - completed / confirmation_required：一行人话摘要 + 默认收起的原始详情
 */

const TOOL_LABELS: Record<string, string> = {
  search_boundary_layer_rules: '规则库检索',
  calculate_smooth_layers: 'Smooth 层数计算',
  calculate_uniform_first_height: 'Uniform 首层高度计算',
  web_search: '网络搜索',
  相关性判断: '规则库相关性判断',
}

const formatNumber = (value: unknown): string => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(Number(value.toFixed(4)))
  }
  return String(value ?? '')
}

const truncate = (value: string, max = 72): string => {
  const text = value.replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}…` : text
}

function parseJson(content: string): Record<string, unknown> | null {
  let current: unknown = content
  // 容忍历史数据的双重 JSON 编码：最多剥三层
  for (let depth = 0; depth < 3 && typeof current === 'string'; depth += 1) {
    try {
      current = JSON.parse(current)
    } catch {
      return null
    }
  }
  if (current && typeof current === 'object' && !Array.isArray(current)) {
    return current as Record<string, unknown>
  }
  return null
}

export function summarizeToolContent(
  toolName: string,
  status: string,
  content: string,
): string {
  const label = TOOL_LABELS[toolName] ?? toolName
  const payload = parseJson(content)

  if (status === 'running') {
    if (payload) {
      if (typeof payload.query === 'string' && payload.query.trim()) {
        return `正在${label}：“${truncate(String(payload.query), 32)}”`
      }
      if ('first_cell_y_plus' in payload) return '正在计算 Smooth 层数…'
      if ('dynamic_viscosity_pa_s' in payload) return '正在计算 Uniform 首层高度…'
    }
    return `正在调用${label}…`
  }

  if (payload) {
    const results = Array.isArray(payload.results)
      ? (payload.results as Array<Record<string, unknown>>)
      : []
    if (results.length && results[0] && 'source' in results[0]) {
      const sources = [...new Set(results.map((item) => String(item.source ?? '')))].filter(Boolean)
      return `命中 ${results.length} 条规则（${truncate(sources.join('、'), 48)}）`
    }
    if (results.length && results[0] && 'href' in results[0]) {
      return `找到 ${results.length} 条网页结果`
    }
    if (payload.status === 'no_match' || (!results.length && 'results' in payload)) {
      return '未命中相关规则'
    }
    if (payload.confirmation_required === true) {
      return `Reynolds 数 ${formatNumber(payload.reynolds_number)} 超出估算适用范围，需确认后继续`
    }
    if (typeof payload.recommended_layers === 'number') {
      return `推荐层数 ${formatNumber(payload.recommended_layers)} 层（首层 y+ ${formatNumber(
        payload.first_cell_y_plus,
      )} → 外层 y+ ${formatNumber(payload.target_outer_y_plus)}，增长率 ${formatNumber(
        payload.growth_rate,
      )}）`
    }
    if (typeof payload.recommended_first_height_mm === 'number') {
      return `估算首层高度 ${formatNumber(payload.recommended_first_height_mm)} mm（Re = ${formatNumber(
        payload.reynolds_number,
      )}）`
    }
    if (typeof payload.should_suggest === 'boolean') {
      const reason = truncate(String(payload.relevance_reason ?? ''), 48)
      return payload.should_suggest ? `判断相关：${reason}` : `判断相关性不足：${reason}`
    }
  }

  const text = content.replace(/\s+/g, ' ').trim()
  return text ? truncate(text) : '已完成'
}

export function AgentToolMessage({
  toolName,
  toolStatus,
  content,
}: {
  toolName: string
  toolStatus: string
  content: string
}) {
  const label = TOOL_LABELS[toolName] ?? toolName
  const summary = summarizeToolContent(toolName, toolStatus, content)

  if (toolStatus === 'running') {
    return (
      <div className="agent-tool-status">
        <span className="agent-tool-spinner" aria-hidden />
        <Typography.Text type="secondary">{summary}</Typography.Text>
      </div>
    )
  }

  let detail = content
  try {
    let parsed: unknown = content
    while (typeof parsed === 'string') {
      parsed = JSON.parse(parsed)
    }
    detail = JSON.stringify(parsed, null, 2)
  } catch {
    // 非 JSON 内容按原文展示
  }

  const isConfirmation = toolStatus === 'confirmation_required'
  return (
    <Collapse
      size="small"
      ghost
      className={`agent-tool-chip${isConfirmation ? ' is-confirmation' : ''}`}
      items={[
        {
          key: 'detail',
          label: (
            <span className="agent-tool-chip-label">
              <Typography.Text type="secondary" className="agent-tool-chip-name">
                {label}
              </Typography.Text>
              <Typography.Text
                type={isConfirmation ? 'warning' : undefined}
                className="agent-tool-chip-summary"
              >
                {summary}
              </Typography.Text>
            </span>
          ),
          children: <pre className="agent-tool-detail">{detail || '（无内容）'}</pre>,
        },
      ]}
    />
  )
}
