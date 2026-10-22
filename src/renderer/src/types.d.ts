import type { FluentAIApi } from '../../shared/contracts'

export {}

declare global {
  interface Window {
    fluentAI?: FluentAIApi
  }
}
