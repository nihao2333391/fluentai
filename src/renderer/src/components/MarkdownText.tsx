import type { ReactNode } from 'react'

/**
 * 轻量 Markdown 渲染组件（零依赖）。
 * 支持：**加粗**、`行内代码`、```围栏代码块```、# 标题、
 * 无序/有序列表、> 引用、--- 分隔线、裸链接自动转超链接、换行。
 * 面向 Agent 聊天消息的有限格式集，不追求完整 Markdown 规范。
 */

const INLINE_TOKEN_RE =
  /(\*\*[^*\n]+\*\*)|(`[^`\n]+`)|(https?:\/\/[^\s<>()[\]{}"'，。；、）】\u3000]+)/g

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = []
  let cursor = 0
  let index = 0
  for (const match of text.matchAll(INLINE_TOKEN_RE)) {
    const start = match.index ?? 0
    if (start > cursor) parts.push(text.slice(cursor, start))
    const token = match[0]
    const key = `${keyPrefix}-i${index++}`
    if (token.startsWith('**')) {
      parts.push(
        <strong key={key} className="md-strong">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      parts.push(
        <code key={key} className="md-code">
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      parts.push(
        <a key={key} href={token} target="_blank" rel="noreferrer">
          {token}
        </a>,
      )
    }
    cursor = start + token.length
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return parts
}

const HEADING_RE = /^(#{1,4})\s+(.*)$/
const BULLET_RE = /^[-*+]\s+(.*)$/
const ORDERED_RE = /^(\d+)[.、)]\s+(.*)$/
const QUOTE_RE = /^>\s?(.*)$/
const HR_RE = /^(---+|\*\*\*+|___+)\s*$/
const FENCE_RE = /^```/

function renderParagraph(lines: string[], key: string): ReactNode {
  return (
    <p key={key} className="md-p">
      {lines.map((line, lineIndex) => (
        <span key={`${key}-l${lineIndex}`}>
          {lineIndex > 0 ? <br /> : null}
          {renderInline(line, `${key}-l${lineIndex}`)}
        </span>
      ))}
    </p>
  )
}

export function MarkdownText({ text, className }: { text: string; className?: string }) {
  const source = (text ?? '').replace(/\r\n/g, '\n')
  if (!source.trim()) return null
  const lines = source.split('\n')
  const blocks: ReactNode[] = []
  let paragraph: string[] = []
  let blockIndex = 0

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(renderParagraph(paragraph, `b${blockIndex++}`))
      paragraph = []
    }
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    if (FENCE_RE.test(line.trim())) {
      flushParagraph()
      const codeLines: string[] = []
      i += 1
      while (i < lines.length && !FENCE_RE.test(lines[i].trim())) {
        codeLines.push(lines[i])
        i += 1
      }
      i += 1
      blocks.push(
        <pre key={`b${blockIndex++}`} className="md-pre">
          {codeLines.join('\n')}
        </pre>,
      )
      continue
    }

    if (!line.trim()) {
      flushParagraph()
      i += 1
      continue
    }

    if (HR_RE.test(line.trim())) {
      flushParagraph()
      blocks.push(<hr key={`b${blockIndex++}`} className="md-hr" />)
      i += 1
      continue
    }

    const heading = line.match(HEADING_RE)
    if (heading) {
      flushParagraph()
      const level = heading[1].length
      blocks.push(
        <div key={`b${blockIndex++}`} className={`md-h md-h${level}`}>
          {renderInline(heading[2], `b${blockIndex}`)}
        </div>,
      )
      i += 1
      continue
    }

    const quote = line.match(QUOTE_RE)
    if (quote) {
      flushParagraph()
      const quoteLines: string[] = []
      while (i < lines.length) {
        const next = lines[i].match(QUOTE_RE)
        if (!next) break
        quoteLines.push(next[1])
        i += 1
      }
      blocks.push(
        <blockquote key={`b${blockIndex++}`} className="md-quote">
          {renderParagraph(quoteLines, `b${blockIndex}`)}
        </blockquote>,
      )
      continue
    }

    const bullet = line.match(BULLET_RE)
    if (bullet) {
      flushParagraph()
      const items: string[] = []
      while (i < lines.length) {
        const next = lines[i].match(BULLET_RE)
        if (!next) break
        items.push(next[1])
        i += 1
      }
      blocks.push(
        <ul key={`b${blockIndex++}`} className="md-list">
          {items.map((item, itemIndex) => (
            <li key={`b${blockIndex}-li${itemIndex}`} className="md-li">
              {renderInline(item, `b${blockIndex}-li${itemIndex}`)}
            </li>
          ))}
        </ul>,
      )
      continue
    }

    const ordered = line.match(ORDERED_RE)
    if (ordered) {
      flushParagraph()
      const items: string[] = []
      while (i < lines.length) {
        const next = lines[i].match(ORDERED_RE)
        if (!next) break
        items.push(next[2])
        i += 1
      }
      blocks.push(
        <ol key={`b${blockIndex++}`} className="md-list">
          {items.map((item, itemIndex) => (
            <li key={`b${blockIndex}-oli${itemIndex}`} className="md-li">
              {renderInline(item, `b${blockIndex}-oli${itemIndex}`)}
            </li>
          ))}
        </ol>,
      )
      continue
    }

    paragraph.push(line)
    i += 1
  }
  flushParagraph()

  return <div className={`md-text${className ? ` ${className}` : ''}`}>{blocks}</div>
}
