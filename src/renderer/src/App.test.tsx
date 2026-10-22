import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the M1 foundation and all planned modules', () => {
    render(<App />)

    expect(screen.getByText('桌面应用基础框架已就绪')).toBeInTheDocument()
    expect(screen.getByText('自动化创建')).toBeInTheDocument()
    expect(screen.getByText('我的自动化')).toBeInTheDocument()
    expect(screen.getByText('我的模型')).toBeInTheDocument()
    expect(screen.getByText('设置')).toBeInTheDocument()
  })
})
