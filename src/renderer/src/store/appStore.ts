import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ThemeMode = 'light' | 'dark' | 'system'
export type Language = 'zh' | 'en'

interface AppPreferences {
  themeMode: ThemeMode
  language: Language
  setThemeMode: (themeMode: ThemeMode) => void
  setLanguage: (language: Language) => void
}

export const useAppStore = create<AppPreferences>()(
  persist(
    (set) => ({
      themeMode: 'system',
      language: 'zh',
      setThemeMode: (themeMode) => set({ themeMode }),
      setLanguage: (language) => set({ language }),
    }),
    {
      name: 'fluent-ai-ui-preferences',
      version: 1,
    },
  ),
)
