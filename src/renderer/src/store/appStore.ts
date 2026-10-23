import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ThemeMode = 'light' | 'dark' | 'system'
interface AppPreferences {
  themeMode: ThemeMode
  setThemeMode: (themeMode: ThemeMode) => void
}

export const useAppStore = create<AppPreferences>()(
  persist(
    (set) => ({
      themeMode: 'system',
      setThemeMode: (themeMode) => set({ themeMode }),
    }),
    {
      name: 'fluent-ai-ui-preferences',
      version: 2,
      migrate: (persistedState) => {
        const state = persistedState as Partial<AppPreferences>
        return { themeMode: state.themeMode ?? 'system' }
      },
    },
  ),
)
