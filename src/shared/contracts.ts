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

export interface Automation {
  id: number
  name: string
  description: string
  preset: PresetDocument
  status: AutomationStatus
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

export interface OpenModelRequest {
  connection?: FluentConnectionConfig | null
  load_case: boolean
}

export interface ModelOpenReport {
  status: 'success' | 'failed'
  model_id: number
  message: string
  connection: FluentStatus | null
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

export interface SyncLogQuery {
  limit?: number
  direction?: SyncLogDirection
  status?: SyncLogStatus
  automationId?: number
  meshingAutomationId?: number
  modelId?: number
  search?: string
}

export interface ModelsApi {
  list: () => Promise<Model[]>
  get: (id: number) => Promise<Model>
  pickFile: () => Promise<PickedModelFile | null>
  create: (payload: ModelCreateRequest) => Promise<Model>
  update: (id: number, payload: ModelUpdateRequest) => Promise<Model>
  open: (id: number, payload: OpenModelRequest) => Promise<ModelOpenReport>
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
  cancel: (id: string) => Promise<Job>
}

export interface SyncLogsApi {
  list: (query?: SyncLogQuery) => Promise<SyncLog[]>
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

export type MeshingWorkflowType = 'watertight' | 'fault-tolerant'
export type MeshingPresetValue =
  PresetValue | MeshingPresetValue[] | { [key: string]: MeshingPresetValue }

export interface MeshingArgumentReference {
  task_path: string[]
  argument_path: string[]
  compound_child_name?: string | null
}

export interface MeshingReadRequest {
  workflow_type: MeshingWorkflowType
  items?: MeshingArgumentReference[]
}

export interface MeshingReadItemResult extends MeshingArgumentReference {
  found: boolean
  value: MeshingPresetValue | null
  error: string | null
}

export interface MeshingReadReport {
  workflow_type: MeshingWorkflowType
  status: 'success' | 'failed'
  task_names: string[]
  items: MeshingReadItemResult[]
  error: string | null
}

export interface MeshingWriteRequest {
  workflow_type: MeshingWorkflowType
  items: MeshingPresetItem[]
  verify: boolean
  create_compound_child?: boolean
}

export interface MeshingWriteReport {
  workflow_type: MeshingWorkflowType
  status: 'success' | 'failed'
  results: MeshingArgumentWriteResult[]
  missing_names?: string[]
  verified: boolean
  error: string | null
}

export interface MeshingWorkflowFieldContract {
  path: string[]
  label: string
  type: string
  control: 'switch' | 'select' | 'multi_select' | 'tag_select' | 'number' | 'text' | string
  enum: unknown[] | null
  default: unknown
  advanced: boolean
  developer: boolean
  display_condition?: string | null
  ui_default_override?: unknown
}

export interface MeshingWorkflowStepContract {
  sequence: number
  task_path: string[]
  english_name: string
  label: string
  task_type: string
  mode?: 'collection' | 'region_table' | string
  fields: MeshingWorkflowFieldContract[]
  toggle_field?: MeshingWorkflowFieldContract | null
  collection?: {
    child_name_field: string | null
    fields: MeshingWorkflowFieldContract[]
  }
  region_name_field?: string[]
  region_type_field?: string[]
  region_type_enum?: string[]
  file_field?: string[]
  primary_field?: string[]
}

export interface MeshingWorkflowContract {
  schema_version: number
  fluent_version: string
  workflow_type: MeshingWorkflowType
  source_schema: string
  step_order: string[]
  conditional_tasks?: Record<string, {
    geometry?: string[]
    argument?: string
    equals?: string
    default?: string
  }>
  steps: MeshingWorkflowStepContract[]
}

export interface MeshingSchemaArgument {
  name: string
  source_name?: string
  display_name?: string
  display_condition?: string | null
  display_text_expression?: string | null
  display_unit?: string | null
  ui_section?: '常规' | '高级选项' | '开发者/内部' | string
  ui_kind?: string
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
  ui_sequence?: number
  ui_display_condition?: string | null
  ui_help_string?: string | null
  ui_source_line?: number | null
}

export interface MeshingWorkflowSchema {
  schema_version: number
  fluent_version: string
  workflow_type: MeshingWorkflowType
  display_name?: string
  generated_at_utc: string
  tasks: MeshingSchemaTask[]
  ui_metadata?: {
    schema_version: number
    source: string
    task_order: string[]
    task_audit: Array<Record<string, unknown>>
  }
}

export interface MeshingSchemaSummary {
  workflow_type: MeshingWorkflowType
  schema_id: string
  fluent_version: string
  task_count: number
  argument_count: number
}

export interface MeshingReferenceInspection {
  model_id: number
  model_name: string
  fluent_version: string | null
  labels: string[]
  message: string
}

export interface MeshingArchiveCreate {
  mesh_path: string
  modeling_notes: string
}

export interface MeshingArchiveRecord {
  id: string
  session_id: string
  automation_id: number
  model_id: number
  mesh_path: string
  record_json_path: string
  record_markdown_path: string
  created_at: string
  difference_count: number
  unavailable_count: number
}

export interface MeshingPresetItem {
  task_path: string[]
  argument_path: string[]
  value: MeshingPresetValue
  value_mode?: 'fixed' | 'at_use'
  required: boolean
  compound_child_name: string | null
}

export interface MeshingPresetDocument {
  schema_version: 1 | 2
  fluent_version: string
  workflow_type: MeshingWorkflowType
  items: MeshingPresetItem[]
  /** Shared face labels available to every local-sizing and boundary-layer child. */
  face_label_catalog?: string[]
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

export interface MeshingArgumentWriteResult {
  task_path: string[]
  argument_path: string[]
  compound_child_name: string | null
  expected: MeshingPresetValue
  actual: MeshingPresetValue | null
  success: boolean
  message: string
}

export interface MeshingLiveSessionStart {
  automation_id: number
  model_ids: number[]
  connection?: FluentConnectionConfig | null
}

export interface MeshingLiveStepRequest {
  step_index: number
}

export interface MeshingLiveWriteRequest extends MeshingLiveStepRequest {
  items: MeshingPresetItem[]
}

export interface MeshingLiveLogEntry {
  sequence: number
  timestamp: string
  level: 'info' | 'success' | 'warning' | 'error'
  message: string
  model_id: number | null
}

export interface MeshingLiveStepState {
  task_path: string[]
  status: 'pending' | 'active' | 'running' | 'completed' | 'failed'
  preset_status?: 'pending' | 'applied' | 'manual'
  duration_ms?: number | null
  message: string
}

export interface MeshingLiveModelState {
  model_id: number
  name: string
  file_path: string
  status: 'pending' | 'importing' | 'ready' | 'completed' | 'failed'
  error: string | null
}

export interface MeshingLiveSessionSnapshot {
  session_id: string
  automation_id: number
  automation_name: string
  workflow_type: MeshingWorkflowType
  status: 'starting' | 'connected' | 'running' | 'waiting' | 'completed' | 'failed' | 'stopped'
  phase?:
    | 'connecting'
    | 'importing'
    | 'preparing_surface'
    | 'preparing_local_sizing'
    | 'executing_local_sizing'
    | 'preparing_surface_mesh'
    | 'surface_ready'
    | 'generating_surface'
    | 'preparing_volume'
    | 'volume_ready'
    | 'generating_volume'
    | 'failed'
    | 'completed'
  phase_elapsed_ms?: number | null
  connection: FluentStatus | null
  models: MeshingLiveModelState[]
  current_model_index: number
  current_step_index: number
  steps: MeshingLiveStepState[]
  logs: MeshingLiveLogEntry[]
  message: string
  native_task_poll_error?: string | null
}

export interface MeshingLiveStepReport {
  status: 'success' | 'failed'
  message: string
  snapshot: MeshingLiveSessionSnapshot
  step_index: number
  task_path: string[]
  write_report: MeshingWriteReport | null
  read_report: MeshingReadReport | null
}

export interface MeshingLiveApi {
  start: (payload: MeshingLiveSessionStart) => Promise<MeshingLiveSessionSnapshot>
  get: (sessionId: string) => Promise<MeshingLiveSessionSnapshot>
  enterStep: (sessionId: string, payload: MeshingLiveStepRequest) => Promise<MeshingLiveStepReport>
  readStep: (sessionId: string, stepIndex: number) => Promise<MeshingLiveStepReport>
  writeStep: (sessionId: string, payload: MeshingLiveWriteRequest) => Promise<MeshingLiveStepReport>
  executeStep: (
    sessionId: string,
    payload: MeshingLiveStepRequest,
  ) => Promise<MeshingLiveStepReport>
  retryPrepare: (sessionId: string) => Promise<MeshingLiveSessionSnapshot>
  nextModel: (sessionId: string) => Promise<MeshingLiveSessionSnapshot>
  retryModel: (sessionId: string) => Promise<MeshingLiveSessionSnapshot>
  stop: (sessionId: string) => Promise<MeshingLiveSessionSnapshot>
  pickMeshFile: () => Promise<string | null>
  archive: (sessionId: string, payload: MeshingArchiveCreate) => Promise<MeshingArchiveRecord>
  archives: (sessionId: string) => Promise<MeshingArchiveRecord[]>
}

export interface DatabaseBackupInfo {
  name: string
  path: string
  size: number
  created_at: string
}

export interface DatabaseBackupList {
  backups: DatabaseBackupInfo[]
}

export interface RestoreDatabaseReport {
  status: 'success' | 'failed'
  backup_name: string
  safety_backup: DatabaseBackupInfo | null
  message: string
}

export interface SystemApi {
  listBackups: () => Promise<DatabaseBackupList>
  createBackup: () => Promise<DatabaseBackupInfo>
  restoreBackup: (backupName: string) => Promise<RestoreDatabaseReport>
}

export interface MeshingApi {
  status: () => Promise<FluentStatus>
  connect: (config: FluentConnectionConfig) => Promise<FluentStatus>
  disconnect: () => Promise<FluentStatus>
  read: (request: MeshingReadRequest) => Promise<MeshingReadReport>
  write: (request: MeshingWriteRequest) => Promise<MeshingWriteReport>
  workflowSchema: (workflowType: MeshingWorkflowType) => Promise<MeshingWorkflowContract>
  schemas: () => Promise<MeshingSchemaSummary[]>
  schema: (workflowType: MeshingWorkflowType) => Promise<MeshingWorkflowSchema>
  validatePreset: (preset: MeshingPresetDocument) => Promise<MeshingPresetValidationReport>
  inspectReferenceModel: (modelId: number) => Promise<MeshingReferenceInspection>
}

export interface MeshingAutomationsApi {
  list: () => Promise<MeshingAutomation[]>
  create: (payload: MeshingAutomationInput) => Promise<MeshingAutomation>
  get: (id: number) => Promise<MeshingAutomation>
  update: (id: number, payload: MeshingAutomationInput) => Promise<MeshingAutomation>
  delete: (id: number) => Promise<void>
  validate: (id: number) => Promise<MeshingPresetValidationReport>
}

export interface FluentAIApi {
  readonly platform: string
  readonly sidecar: SidecarApi
  readonly models: ModelsApi
  readonly settings: SettingsApi
  readonly jobs: JobsApi
  readonly syncLogs: SyncLogsApi
  readonly system: SystemApi
  readonly credentials: CredentialsApi
  readonly fluent: FluentApi
  readonly meshing: MeshingApi
  readonly meshingLive: MeshingLiveApi
  readonly meshingAutomations: MeshingAutomationsApi
}
