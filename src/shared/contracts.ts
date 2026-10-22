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
  meshing_automation_id: number | null
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

export type FluentLaunchMode = 'launch' | 'attach'
export type FluentUiMode = 'no_gui' | 'no_graphics' | 'hidden_gui' | 'gui'

export interface FluentConnectionConfig {
  mode: FluentLaunchMode
  fluent_path?: string | null
  product_version: string
  processor_count: number
  ui_mode: FluentUiMode
  start_timeout: number
  cleanup_on_exit: boolean
  host: string
  port?: number | null
  password?: string | null
  server_info_file?: string | null
}

export interface FluentStatus {
  connected: boolean
  mode: FluentLaunchMode | null
  version: string | null
  pid: number | null
  host: string | null
  port: number | null
}

export type FluentSettingGroup = 'general' | 'models' | 'solution' | 'reference'

export interface SettingCatalogEntry {
  setting_id: string
  display_name: string
  group: FluentSettingGroup
  value_type: PresetType
  allowed_values: PresetValue[] | null
  minimum: number | null
  maximum: number | null
  description: string
}

export interface SettingWriteResult {
  setting_id: string
  expected: PresetValue
  actual: PresetValue
  success: boolean
  message: string
}

export interface FluentOperationReport {
  operation: 'write' | 'apply'
  status: 'success' | 'failed'
  results: SettingWriteResult[]
  rollback_attempted: boolean
  rollback_succeeded: boolean | null
  rollback_results: SettingWriteResult[]
}

export interface PresetValidationReport {
  valid: boolean
  errors: string[]
  normalized_items: PresetItem[]
}

export interface ApplyAutomationRequest {
  model_id: number
  connection?: FluentConnectionConfig | null
  load_case: boolean
}

export interface WorkflowReport {
  status: 'success' | 'failed'
  automation_id: number
  model_id: number
  job_id: string
  message: string
  connection: FluentStatus | null
  apply_report: FluentOperationReport | null
  sync_log_id: number | null
}

export interface FluentApi {
  status: () => Promise<FluentStatus>
  connect: (config: FluentConnectionConfig) => Promise<FluentStatus>
  disconnect: () => Promise<FluentStatus>
  catalog: () => Promise<SettingCatalogEntry[]>
  readSettings: (settingIds: string[]) => Promise<Record<string, PresetValue>>
  writeSettings: (items: PresetItem[]) => Promise<FluentOperationReport>
  validatePreset: (preset: PresetDocument) => Promise<PresetValidationReport>
  applyPreset: (preset: PresetDocument) => Promise<FluentOperationReport>
}

export interface WorkflowsApi {
  applyAutomation: (
    automationId: number,
    payload: ApplyAutomationRequest,
  ) => Promise<WorkflowReport>
}

export type MeshingWorkflowType = 'watertight' | 'fault-tolerant'
export type MeshingPresetValue =
  PresetValue | MeshingPresetValue[] | { [key: string]: MeshingPresetValue }

export interface MeshingSchemaArgument {
  name: string
  source_name?: string
  edit_path: string
  value_type: string
  current_value: unknown
  allowed_values: MeshingPresetValue[] | null
  default_value: unknown
  read_only: boolean | null
  editable?: boolean
  active: boolean | null
  exposure_level: string | number | null
  children: MeshingSchemaArgument[]
  error?: string
  note?: string
}

export interface MeshingSchemaTask {
  python_name: string
  display_name: string
  command_name: string
  task_type: 'Simple' | 'Compound' | 'Conditional' | 'Compound Child' | string
  check_point: string
  state: string
  task_list: string[] | string | null
  inactive_task_list: string[] | string | null
  inactive_tasks: string[]
  insertable_tasks: string[]
  arguments: MeshingSchemaArgument[]
  children: MeshingSchemaTask[]
  supports_child_template?: boolean
  child_template?: MeshingSchemaTask | null
  child_template_error?: string
  child_template_warning?: string
  template?: boolean
  template_task_path?: string[]
  template_source?: 'fluent_add_child_and_update' | 'parent_command_arguments' | string
}

export interface MeshingWorkflowSchema {
  schema_version: number
  fluent_version: string
  workflow_type: MeshingWorkflowType
  display_name?: string
  generated_at_utc: string
  tasks: MeshingSchemaTask[]
}

export interface MeshingSchemaSummary {
  workflow_type: MeshingWorkflowType
  schema_id: string
  fluent_version: string
  task_count: number
  argument_count: number
}

export interface MeshingPresetItem {
  task_path: string[]
  argument_path: string[]
  value: MeshingPresetValue
  required: boolean
  compound_child_name: string | null
}

export interface MeshingPresetDocument {
  schema_version: 1
  fluent_version: string
  workflow_type: MeshingWorkflowType
  items: MeshingPresetItem[]
}

export interface MeshingAutomationInput {
  name: string
  description: string
  model_family: string
  reference_model_id: number | null
  preset: MeshingPresetDocument
  status: 'draft' | 'active'
}

export interface MeshingAutomation extends MeshingAutomationInput {
  id: number
  created_at: string
  updated_at: string
}

export interface MeshingPresetValidationReport {
  valid: boolean
  errors: string[]
  schema_id: string
  item_count: number
}

export interface ApplyMeshingAutomationRequest {
  model_id: number
  connection?: FluentConnectionConfig | null
  import_geometry: boolean
}

export interface MeshingArgumentWriteResult {
  task_path: string[]
  argument_path: string[]
  compound_child_name: string | null
  expected: MeshingPresetValue
  actual: MeshingPresetValue | null
  success: boolean
  message: string
}

export interface MeshingNameCheck {
  kind: 'label' | 'zone' | 'region' | 'object' | 'selection'
  name: string
  found: boolean
}

export interface MeshingApplyReport {
  workflow_type: MeshingWorkflowType
  status: 'success' | 'failed'
  results: MeshingArgumentWriteResult[]
  name_checks: MeshingNameCheck[]
  created_children: string[]
  stopped_before: string[]
  imported_model: string | null
  missing_names: string[]
  error: string | null
}

export interface MeshingWorkflowReport {
  status: 'success' | 'failed'
  automation_id: number
  model_id: number
  job_id: string
  message: string
  connection: FluentStatus | null
  apply_report: MeshingApplyReport | null
  sync_log_id: number | null
}

export interface MeshingApi {
  schemas: () => Promise<MeshingSchemaSummary[]>
  schema: (workflowType: MeshingWorkflowType) => Promise<MeshingWorkflowSchema>
  validatePreset: (preset: MeshingPresetDocument) => Promise<MeshingPresetValidationReport>
}

export interface MeshingAutomationsApi {
  list: () => Promise<MeshingAutomation[]>
  create: (payload: MeshingAutomationInput) => Promise<MeshingAutomation>
  get: (id: number) => Promise<MeshingAutomation>
  update: (id: number, payload: MeshingAutomationInput) => Promise<MeshingAutomation>
  delete: (id: number) => Promise<void>
  validate: (id: number) => Promise<MeshingPresetValidationReport>
  apply: (id: number, payload: ApplyMeshingAutomationRequest) => Promise<MeshingWorkflowReport>
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
  readonly fluent: FluentApi
  readonly workflows: WorkflowsApi
  readonly meshing: MeshingApi
  readonly meshingAutomations: MeshingAutomationsApi
}
