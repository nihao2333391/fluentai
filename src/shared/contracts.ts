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

export type PresetValue = number | boolean | string | null
export type PresetType = 'int' | 'float' | 'bool' | 'string' | 'enum'
export type AutomationStatus = 'draft' | 'active'

export interface PresetItem {
  setting_id: string
  type: PresetType
  value: PresetValue
  required: boolean
}

export interface PresetDocument {
  schema_version: 1
  fluent_version: string | null
  items: PresetItem[]
}

export interface AutomationInput {
  name: string
  description: string
  preset: PresetDocument
  status: AutomationStatus
}

export interface Automation extends AutomationInput {
  id: number
  created_at: string
  updated_at: string
}

export interface Model {
  id: number
  name: string
  file_path: string
  file_size: number
  file_mtime: string | null
  description: string
  tags: string[]
  automation_ids: number[]
  default_automation_id: number | null
  created_at: string
  updated_at: string
}

export interface PickedModelFile {
  fileToken: string
  filePath: string
  fileName: string
  size: number
  modifiedAt: string
  extension: string
}

export interface ModelCreateRequest {
  name: string
  fileToken: string
  description?: string
  tags?: string[]
}

export interface ModelUpdateRequest {
  name: string
  fileToken?: string
  description?: string
  tags?: string[]
}

export interface ModelAssociationRequest {
  automationId: number
  isDefault: boolean
}

export interface SettingsPayload {
  values: Record<string, string>
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface Job {
  id: string
  job_type: string
  status: JobStatus
  progress: number
  message: string
  payload: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export type SyncLogDirection = 'read' | 'write' | 'sync' | 'apply' | 'pull'
export type SyncLogStatus = 'success' | 'failed'

export interface SyncLog {
  id: number
  direction: SyncLogDirection
  target: string
  automation_id: number | null
  model_id: number | null
  payload: Record<string, unknown>
  status: SyncLogStatus
  message: string
  created_at: string
}

export interface AutomationsApi {
  list: () => Promise<Automation[]>
  create: (payload: AutomationInput) => Promise<Automation>
  get: (id: number) => Promise<Automation>
  update: (id: number, payload: AutomationInput) => Promise<Automation>
  delete: (id: number) => Promise<void>
}

export interface ModelsApi {
  list: () => Promise<Model[]>
  get: (id: number) => Promise<Model>
  pickFile: () => Promise<PickedModelFile | null>
  create: (payload: ModelCreateRequest) => Promise<Model>
  update: (id: number, payload: ModelUpdateRequest) => Promise<Model>
  associate: (id: number, payload: ModelAssociationRequest) => Promise<Model>
  refresh: (id: number) => Promise<Model>
  delete: (id: number) => Promise<void>
}

export interface SettingsApi {
  get: () => Promise<SettingsPayload>
  update: (payload: SettingsPayload) => Promise<SettingsPayload>
}

export interface JobsApi {
  list: (limit?: number) => Promise<Job[]>
  get: (id: string) => Promise<Job>
}

export interface SyncLogsApi {
  list: (limit?: number) => Promise<SyncLog[]>
}

export interface CredentialStatus {
  encryptionAvailable: boolean
  configured: boolean
}

export interface CredentialsApi {
  getStatus: () => Promise<CredentialStatus>
  setFluentPassword: (password: string) => Promise<CredentialStatus>
  clearFluentPassword: () => Promise<CredentialStatus>
}

export interface FluentAIApi {
  readonly platform: string
  readonly sidecar: SidecarApi
  readonly automations: AutomationsApi
  readonly models: ModelsApi
  readonly settings: SettingsApi
  readonly jobs: JobsApi
  readonly syncLogs: SyncLogsApi
  readonly credentials: CredentialsApi
}
