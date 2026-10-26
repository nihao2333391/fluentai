import i18n from './index'
import { ansysZhTerms } from './ansysZhTerms'

export const localizedAnsysTerm = (source: string, fallback?: string): string => {
  if (!i18n.language.toLowerCase().startsWith('zh')) return source
  return ansysZhTerms[source] ?? fallback ?? source
}

export const localizedAnsysValue = (value: string): string => localizedAnsysTerm(value)
