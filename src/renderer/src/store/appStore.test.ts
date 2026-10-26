import { beforeEach, describe, expect, it } from 'vitest'

import { useAppStore } from './appStore'

const STORAGE_KEY = 'fluent-ai-ui-preferences'

describe('app preferences', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('persists the selected interface language', () => {
    useAppStore.getState().setLanguage('en')

    const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as {
      state?: { language?: string }
    }
    expect(persisted.state?.language).toBe('en')
  })

  it('restores the selected language from local storage', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ state: { themeMode: 'dark', language: 'zh' }, version: 3 }),
    )

    await useAppStore.persist.rehydrate()

    expect(useAppStore.getState().themeMode).toBe('dark')
    expect(useAppStore.getState().language).toBe('zh')
  })
})
