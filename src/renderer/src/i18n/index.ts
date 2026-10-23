import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { resources } from './resources'

export type AppLanguage = 'zh' | 'en'

export const getSystemLanguage = (): AppLanguage => {
  const locale = (navigator.languages?.[0] ?? navigator.language ?? 'zh').toLowerCase()
  return locale.startsWith('zh') ? 'zh' : 'en'
}

export const systemLanguage = getSystemLanguage()

void i18n.use(initReactI18next).init({
  resources,
  lng: systemLanguage,
  fallbackLng: systemLanguage,
  interpolation: {
    escapeValue: false,
  },
  returnNull: false,
})

export default i18n
