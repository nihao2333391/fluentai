export {}

declare global {
  interface Window {
    fluentAI?: {
      readonly platform: string
    }
  }
}
