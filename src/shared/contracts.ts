export type SidecarState = 'stopped' | 'starting' | 'ready' | 'restarting' | 'error'

export interface SidecarStatus {
  state: SidecarState
  message?: string
  version?: string
  pid?: number
  port?: number
}

export interface SidecarReadyResponse {
  status: 'ready'
  service: 'fluent-ai-sidecar'
  version: string
  pid: number
  database: 'ready'
  timestamp: string
}

export interface SidecarReadyHandshake {
  event: 'sidecar_ready'
  port: number
  pid: number
  version: string
  host: '127.0.0.1'
}

export interface SidecarErrorHandshake {
  event: 'sidecar_error'
  message: string
}

export type SidecarHandshake = SidecarReadyHandshake | SidecarErrorHandshake

export interface SidecarApi {
  getStatus: () => Promise<SidecarStatus>
  restart: () => Promise<SidecarStatus>
  onStatusChanged: (listener: (status: SidecarStatus) => void) => () => void
}

export interface FluentAIApi {
  readonly platform: string
  readonly sidecar: SidecarApi
}
