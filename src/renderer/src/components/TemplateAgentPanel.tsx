import {
  CheckOutlined,
  CloseOutlined,
  SendOutlined,
  StopOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Collapse, Flex, Input, Space, Tag, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AgentToolMessage } from './AgentToolMessage'
import { MarkdownText } from './MarkdownText'

import type {
  AgentImageAttachment,
  AgentMessage,
  AgentModelConfig,
  AgentProactiveSuggestion,
  AgentRunEvent,
} from '../../../shared/contracts'

interface PanelMessage extends AgentMessage {
  toolName?: string
  toolStatus?: string
}

interface TemplateAgentPanelProps {
  templateId: number | null
  activeStep?: string
}

const createLocalMessage = (
  role: 'user' | 'assistant',
  content: string,
  attachments: AgentImageAttachment[] = [],
): PanelMessage => ({
  id: crypto.randomUUID(),
  role,
  content,
  run_id: null,
  status: null,
  created_at: new Date().toISOString(),
  attachments,
})

const readImageFile = (file: File): Promise<AgentImageAttachment> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`读取图片失败：${file.name}`))
    reader.onload = () => {
      const dataUrl = String(reader.result ?? '')
      const encoded = dataUrl.split(',', 2)[1]
      if (!encoded) {
        reject(new Error(`图片数据无效：${file.name}`))
        return
      }
      resolve({
        filename: file.name,
        mime_type: file.type as AgentImageAttachment['mime_type'],
        data_base64: encoded,
      })
    }
    reader.readAsDataURL(file)
  })

export function TemplateAgentPanel({ templateId, activeStep = '' }: TemplateAgentPanelProps) {
  const api = window.fluentAI?.agent
  const navigate = useNavigate()
  const [config, setConfig] = useState<AgentModelConfig | null>(null)
  const [messages, setMessages] = useState<PanelMessage[]>([])
  const [loadedTemplateId, setLoadedTemplateId] = useState<number | null>(null)
  const [proactiveSuggestions, setProactiveSuggestions] = useState<AgentProactiveSuggestion[]>([])
  const [text, setText] = useState('')
  const [pendingImages, setPendingImages] = useState<AgentImageAttachment[]>([])
  const [collapsed, setCollapsed] = useState(false)
  const [running, setRunning] = useState(false)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [needsRangeConfirmation, setNeedsRangeConfirmation] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const pendingEventsRef = useRef(new Map<string, AgentRunEvent[]>())
  const proactiveRequestsRef = useRef(new Set<string>())
  const configured = Boolean(config?.enabled && config.connection_status === 'passed')
  const currentStageKey = activeStep.trim() || 'page_open'

  const handleEvent = useCallback(
    (event: AgentRunEvent): void => {
      if (event.type === 'started') {
        setRunning(true)
        setMessages((current) => [...current, createLocalMessage('assistant', '')])
        return
      }
      if (event.type === 'content') {
        setMessages((current) => {
          const last = current.at(-1)
          if (!last || last.role !== 'assistant')
            return [...current, createLocalMessage('assistant', event.content ?? '')]
          return [
            ...current.slice(0, -1),
            { ...last, content: last.content + (event.content ?? '') },
          ]
        })
        return
      }
      if (event.type === 'tool') {
        setMessages((current) => [
          ...current,
          {
            ...createLocalMessage('assistant', event.content ?? ''),
            toolName: event.tool_name,
            toolStatus: event.tool_status,
          },
        ])
        return
      }
      if (event.type === 'confirmation_required') {
        setNeedsRangeConfirmation(true)
        return
      }
      if (event.type === 'error') setError(event.content ?? 'Agent 运行失败。')
      if (event.type === 'completed' || event.type === 'error') {
        setRunning(false)
        setRequestId(null)
        if (templateId && api) {
          void api.getSession(templateId).then((session) => {
            setMessages(session.messages)
            setLoadedTemplateId(templateId)
            setNeedsRangeConfirmation(session.needs_range_confirmation)
            setProactiveSuggestions(session.proactive_suggestions ?? [])
          })
        }
      }
    },
    [api, templateId],
  )

  useEffect(() => {
    if (!api) return
    let active = true
    void api
      .getModelConfig()
      .then((value) => {
        if (active) setConfig(value)
      })
      .catch(() => {
        if (active) setConfig(null)
      })
    return () => {
      active = false
    }
  }, [api])

  useEffect(() => {
    if (!templateId) return
    if (!api) return
    let active = true
    void api
      .getSession(templateId)
      .then((session) => {
        if (active) {
          setMessages(session.messages)
          setLoadedTemplateId(templateId)
          setNeedsRangeConfirmation(session.needs_range_confirmation)
          setProactiveSuggestions(session.proactive_suggestions ?? [])
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : String(loadError))
      })
    return () => {
      active = false
    }
  }, [api, templateId])

  useEffect(() => {
    if (!configured || !templateId || !api) return
    const stageKey = currentStageKey
    const requestKey = `${templateId}:${stageKey}`
    if (proactiveRequestsRef.current.has(requestKey)) return
    proactiveRequestsRef.current.add(requestKey)
    void api
      .getProactiveSuggestion(templateId, stageKey)
      .then((suggestion) => {
        if (!suggestion?.should_suggest) return
        setProactiveSuggestions((current) =>
          current.some((item) => item.run_id === suggestion.run_id)
            ? current
            : [...current, suggestion],
        )
      })
      .catch(() => {
        // Proactive retrieval is optional; ordinary chat remains available.
      })
  }, [api, configured, currentStageKey, templateId])

  useEffect(() => {
    if (!api) return
    const unsubscribe = api.onEvent(({ requestId: incomingId, payload }) => {
      if (incomingId === requestId) {
        handleEvent(payload)
        return
      }
      const pending = pendingEventsRef.current.get(incomingId) ?? []
      pending.push(payload)
      pendingEventsRef.current.set(incomingId, pending)
    })
    return unsubscribe
  }, [api, handleEvent, requestId])

  useEffect(() => {
    if (!requestId) return
    const pending = pendingEventsRef.current.get(requestId)
    if (!pending) return
    pendingEventsRef.current.delete(requestId)
    for (const event of pending) handleEvent(event)
  }, [handleEvent, requestId])

  useEffect(() => {
    const node = scrollRef.current
    if (node && node.scrollHeight - node.scrollTop - node.clientHeight < 80) {
      node.scrollTop = node.scrollHeight
    }
  }, [messages])

  const send = async (value = text, confirmOutOfRange = false): Promise<void> => {
    const outgoingImages = confirmOutOfRange ? [] : pendingImages
    const message = value.trim() || (outgoingImages.length ? '请直接查看并分析我附上的图片。' : '')
    if (!message || running || !templateId || !api) return
    setError(null)
    setMessages((current) => [...current, createLocalMessage('user', message, outgoingImages)])
    if (!confirmOutOfRange) {
      setText('')
      setPendingImages([])
    }
    try {
      const id = outgoingImages.length
        ? await api.sendMessage(templateId, message, confirmOutOfRange, outgoingImages)
        : await api.sendMessage(templateId, message, confirmOutOfRange)
      if (confirmOutOfRange) setNeedsRangeConfirmation(false)
      setRequestId(id)
      setRunning(true)
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : String(sendError))
    }
  }

  const stop = async (): Promise<void> => {
    if (!requestId || !api) return
    await api.stopMessage(requestId)
    setRunning(false)
    setRequestId(null)
  }

  const visibleMessages = useMemo(() => {
    if (loadedTemplateId !== templateId) return []
    const toolOf = (item: PanelMessage) => item.tool_name ?? item.toolName ?? null
    const statusOf = (item: PanelMessage) => item.tool_status ?? item.toolStatus ?? null
    // 同一 run 内同名工具一旦完成，隐藏多余的 running 占位，避免刷屏
    const completedToolKeys = new Set(
      messages
        .filter((item) => toolOf(item) && statusOf(item) !== 'running')
        .map((item) => `${item.run_id}:${toolOf(item)}`),
    )
    return messages.filter((item) => {
      const tool = toolOf(item)
      if (!tool) return true
      if (statusOf(item) !== 'running') return true
      return !completedToolKeys.has(`${item.run_id}:${tool}`)
    })
  }, [loadedTemplateId, messages, templateId])

  if (collapsed) {
    return (
      <Button
        className="template-agent-rail"
        icon={<SendOutlined />}
        onClick={() => setCollapsed(false)}
      >
        工程辅助 Agent
      </Button>
    )
  }

  return (
    <Card
      className="template-agent-panel"
      styles={{ body: { padding: 0, height: 'calc(100% - 49px)', minHeight: 0 } }}
      title={
        <Flex align="center" gap={8}>
          <Typography.Text strong>工程辅助 Agent</Typography.Text>
          <Tag color={running ? 'processing' : configured ? 'success' : 'default'}>
            {running ? '处理中' : configured ? config?.display_name : '模型未配置'}
          </Tag>
        </Flex>
      }
      extra={
        <Space size={4}>
          <Button type="text" size="small" onClick={() => navigate('/settings')}>
            设置模型
          </Button>
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={() => setCollapsed(true)}
          />
        </Space>
      }
    >
      <div className="template-agent-body">
        <div className="template-agent-messages" ref={scrollRef}>
          {configured && loadedTemplateId === templateId
            ? proactiveSuggestions
                .filter((suggestion) => suggestion.stage_key === currentStageKey)
                .map((suggestion) => (
                  <Card
                    key={suggestion.run_id}
                    size="small"
                    className="template-agent-suggestion"
                    title="Agent 主动建议"
                  >
                    <MarkdownText text={suggestion.suggestion} />
                    {suggestion.follow_up_questions.length ? (
                      <Space wrap>
                        {suggestion.follow_up_questions.map((question) => (
                          <Button
                            key={question}
                            size="small"
                            disabled={running}
                            onClick={() => void send(question)}
                          >
                            {question}
                          </Button>
                        ))}
                      </Space>
                    ) : null}
                    <Typography.Paragraph type="secondary" style={{ margin: '12px 0 0' }}>
                      来源：
                      {suggestion.sources
                        .map(({ source, section }) => `${source} · ${section}`)
                        .join('；')}
                    </Typography.Paragraph>
                    {suggestion.execution_records.length ? (
                      <Collapse
                        size="small"
                        ghost
                        items={[
                          {
                            key: 'execution',
                            label: (
                              <Typography.Text type="secondary">
                                检索与判断记录（{suggestion.execution_records.length}）
                              </Typography.Text>
                            ),
                            children: suggestion.execution_records.map((record, index) => (
                              <AgentToolMessage
                                key={`${record.tool_name}-${index}`}
                                toolName={record.tool_name}
                                toolStatus={record.status === 'running' ? 'running' : 'completed'}
                                content={
                                  typeof record.result === 'string' && record.result.trim()
                                    ? record.result
                                    : JSON.stringify(record.result ?? record.target ?? {})
                                }
                              />
                            )),
                          },
                        ]}
                      />
                    ) : null}
                  </Card>
                ))
            : null}
          {visibleMessages.map((item) => {
            const toolName = item.tool_name ?? item.toolName
            if (toolName) {
              return (
                <AgentToolMessage
                  key={item.id}
                  toolName={toolName}
                  toolStatus={item.tool_status ?? item.toolStatus ?? 'completed'}
                  content={item.content ?? ''}
                />
              )
            }
            return (
              <Card
                key={item.id}
                size="small"
                className={`template-agent-message is-${item.role}`}
              >
                {item.attachments?.length ? (
                  <div className="template-agent-attachments">
                    {item.attachments.map((image, index) => (
                      <img
                        key={`${item.id}-${index}`}
                        src={`data:${image.mime_type};base64,${image.data_base64}`}
                        alt={image.filename}
                        title={image.filename}
                      />
                    ))}
                  </div>
                ) : null}
                {item.content
                  ? item.role === 'assistant'
                    ? <MarkdownText text={item.content} />
                    : (
                        <Typography.Paragraph
                          style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}
                        >
                          {item.content}
                        </Typography.Paragraph>
                      )
                  : null}
              </Card>
            )
          })}
          {error ? <Alert type="error" showIcon message={error} /> : null}
        </div>
        {needsRangeConfirmation ? (
          <Alert
            type="warning"
            showIcon
            message="Uniform 的 Reynolds 数超出当前估算范围。"
            description="确认接受摩擦关联式假设后，Agent 才会继续计算首层高度。"
            action={
              <Button
                size="small"
                disabled={running}
                onClick={() =>
                  void send('我确认接受当前 Reynolds 数范围外的估算假设，请继续计算。', true)
                }
              >
                确认并继续
              </Button>
            }
          />
        ) : null}
        {!configured ? (
          <Alert
            type="info"
            showIcon
            message="请先到设置页配置并启用全局 AI 模型。"
            action={
              <Button size="small" onClick={() => navigate('/settings')}>
                去设置
              </Button>
            }
          />
        ) : null}
        {configured && config?.tool_status !== 'passed' ? (
          <Alert
            type="warning"
            showIcon
            message="当前模型尚未通过工具调用测试。"
            description="Agent 可以继续交流方法和工况；边界层数值工具暂不可用。请到设置页完成工具能力检测。"
          />
        ) : null}
        {!templateId ? (
          <Typography.Text type="secondary">保存模板名称和参数后即可开始对话。</Typography.Text>
        ) : null}
        <div className="template-agent-composer">
          {pendingImages.length ? (
            <div className="template-agent-attachments is-pending">
              {pendingImages.map((image, index) => (
                <div className="template-agent-attachment" key={`${image.filename}-${index}`}>
                  <img
                    src={`data:${image.mime_type};base64,${image.data_base64}`}
                    alt={image.filename}
                    title={image.filename}
                  />
                  <Button
                    size="small"
                    type="text"
                    aria-label={`移除图片 ${image.filename}`}
                    icon={<CloseOutlined />}
                    onClick={() =>
                      setPendingImages((current) => current.filter((_, i) => i !== index))
                    }
                  />
                </div>
              ))}
            </div>
          ) : null}
          <input
            ref={imageInputRef}
            hidden
            aria-label="选择图片附件"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            onChange={(event) => {
              const selected = Array.from(event.currentTarget.files ?? [])
              event.currentTarget.value = ''
              void (async () => {
                if (pendingImages.length + selected.length > 4) {
                  setError('每条消息最多上传 4 张图片。')
                  return
                }
                for (const file of selected) {
                  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
                    setError('图片格式支持 PNG、JPEG 和 WebP。')
                    return
                  }
                  if (file.size > 5 * 1024 * 1024) {
                    setError(`图片不能超过 5 MB：${file.name}`)
                    return
                  }
                }
                try {
                  const loaded = await Promise.all(selected.map(readImageFile))
                  setPendingImages((current) => [...current, ...loaded])
                  setError(null)
                } catch (loadError) {
                  setError(loadError instanceof Error ? loadError.message : String(loadError))
                }
              })()
            }}
          />
          <Input.TextArea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
            autoSize={{ minRows: 1, maxRows: 5 }}
            placeholder="描述模型、工况或你想了解的问题…"
            disabled={!configured || !templateId || running}
          />
          <Button
            icon={<UploadOutlined />}
            disabled={!configured || !templateId || running}
            aria-label="上传图片"
            onClick={() => imageInputRef.current?.click()}
          />
          {running ? (
            <Button danger icon={<StopOutlined />} onClick={() => void stop()}>
              停止
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<CheckOutlined />}
              disabled={!configured || !templateId || (!text.trim() && !pendingImages.length)}
              onClick={() => void send()}
            >
              发送
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}
