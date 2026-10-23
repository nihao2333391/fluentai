import { beforeEach, describe, expect, it, vi } from 'vitest'

const setNavigatorLocale = (locale: string): void => {
  Object.defineProperty(window.navigator, 'language', {
    configurable: true,
    value: locale,
  })
  Object.defineProperty(window.navigator, 'languages', {
    configurable: true,
    value: [locale],
  })
}

describe('system language selection', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('uses Chinese when the operating system locale is Chinese', async () => {
    setNavigatorLocale('zh-CN')
    const { getSystemLanguage, systemLanguage } = await import('./index')

    expect(getSystemLanguage()).toBe('zh')
    expect(systemLanguage).toBe('zh')
  })

  it('uses English for non-Chinese system locales', async () => {
    setNavigatorLocale('en-US')
    const { getSystemLanguage, systemLanguage } = await import('./index')

    expect(getSystemLanguage()).toBe('en')
    expect(systemLanguage).toBe('en')
  })
})
