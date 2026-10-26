import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { systemLanguage, type AppLanguage } from '../i18n'

export type ThemeMode = 'light' | 'dark' | 'system'
interface AppPreferences {
  themeMode: ThemeMode
  language: AppLanguage
  setThemeMode: (themeMode: ThemeMode) => void
  setLanguage: (language: AppLanguage) => void
}

export const useAppStore = create<AppPreferences>()(
  persist(
    (set) => ({
      themeMode: 'system',
      language: systemLanguage,
      setThemeMode: (themeMode) => set({ themeMode }),
      setLanguage: (language) => set({ language }),
    }),
    {
      name: 'fluent-ai-ui-preferences',
      version: 3,
      migrate: (persistedState) => {
        const state = persistedState as Partial<AppPreferences>
        return {
          themeMode: state.themeMode ?? 'system',
          language:
            state.language === 'zh' || state.language === 'en' ? state.language : systemLanguage,
        }
      },
    },
  ),
)
