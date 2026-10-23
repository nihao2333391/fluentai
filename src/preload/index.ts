import { contextBridge, ipcRenderer } from 'electron'

import type {
  ApplyAutomationRequest,
  ApplyMeshingAutomationRequest,
  Automation,
  AutomationInput,
  CredentialStatus,
  DatabaseBackupInfo,
  DatabaseBackupList,
  FluentConnectionConfig,
  FluentOperationReport,
  FluentStatus,
  FluentAIApi,
  Job,
  MeshingAutomation,
  MeshingAutomationInput,
  MeshingPresetDocument,
  MeshingPresetValidationReport,
  MeshingReadReport,
  MeshingReadRequest,
  MeshingSchemaSummary,
  MeshingWorkflowSchema,
  MeshingWorkflowType,
  MeshingWorkflowReport,
  MeshingWriteReport,
  MeshingWriteRequest,
  Model,
  ModelAssociationRequest,
  ModelCreateRequest,
  ModelOpenReport,
  ModelUpdateRequest,
  OpenModelRequest,
  PickedModelFile,
  PresetDocument,
  PresetItem,
  PresetValidationReport,
  PresetValue,
  RecentSession,
  RestoreDatabaseReport,
  SettingCatalogEntry,
  SettingsPayload,
  SidecarStatus,
  SyncLog,
  SyncLogQuery,
  WorkflowReport,
} from '../shared/contracts'

const invoke = <T>(channel: string, ...args: unknown[]): Promise<T> =>
  ipcRenderer.invoke(channel, ...args) as Promise<T>

const api: FluentAIApi = Object.freeze({
  platform: process.platform,
  sidecar: Object.freeze({
    getStatus: () => invoke<SidecarStatus>('sidecar:get-status'),
    restart: () => invoke<SidecarStatus>('sidecar:restart'),
    onStatusChanged: (listener: (status: SidecarStatus) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, status: SidecarStatus): void => {
        listener(status)
      }
      ipcRenderer.on('sidecar:status-changed', handler)
      return () => {
        ipcRenderer.off('sidecar:status-changed', handler)
      }
    },
  }),
  automations: Object.freeze({
    list: () => invoke<Automation[]>('automations:list'),
    create: (payload: AutomationInput) => invoke<Automation>('automations:create', payload),
    get: (id: number) => invoke<Automation>('automations:get', id),
    update: (id: number, payload: AutomationInput) =>
      invoke<Automation>('automations:update', id, payload),
    delete: (id: number) => invoke<void>('automations:delete', id),
  }),
  models: Object.freeze({
    list: () => invoke<Model[]>('models:list'),
    get: (id: number) => invoke<Model>('models:get', id),
    pickFile: () => invoke<PickedModelFile | null>('models:pick-file'),
    create: (payload: ModelCreateRequest) => invoke<Model>('models:create', payload),
    update: (id: number, payload: ModelUpdateRequest) =>
      invoke<Model>('models:update', id, payload),
    associate: (id: number, payload: ModelAssociationRequest) =>
      invoke<Model>('models:associate', id, payload),
    open: (id: number, payload: OpenModelRequest) =>
      invoke<ModelOpenReport>('models:open', id, payload),
    refresh: (id: number) => invoke<Model>('models:refresh', id),
    delete: (id: number) => invoke<void>('models:delete', id),
  }),
  settings: Object.freeze({
    get: () => invoke<SettingsPayload>('settings:get'),
    update: (payload: SettingsPayload) => invoke<SettingsPayload>('settings:update', payload),
  }),
  jobs: Object.freeze({
    list: (limit = 50) => invoke<Job[]>('jobs:list', limit),
    get: (id: string) => invoke<Job>('jobs:get', id),
    cancel: (id: string) => invoke<Job>('jobs:cancel', id),
  }),
  syncLogs: Object.freeze({
    list: (query: SyncLogQuery = {}) => invoke<SyncLog[]>('sync-logs:list', query),
  }),
  session: Object.freeze({
    recent: () => invoke<RecentSession>('session:recent'),
  }),
  system: Object.freeze({
    listBackups: () => invoke<DatabaseBackupList>('system:list-backups'),
    createBackup: () => invoke<DatabaseBackupInfo>('system:create-backup'),
    restoreBackup: (backupName: string) =>
      invoke<RestoreDatabaseReport>('system:restore-backup', backupName),
  }),
  credentials: Object.freeze({
    getStatus: () => invoke<CredentialStatus>('credentials:status'),
    setFluentPassword: (password: string) =>
      invoke<CredentialStatus>('credentials:set-fluent-password', password),
    clearFluentPassword: () => invoke<CredentialStatus>('credentials:clear-fluent-password'),
  }),
  meshing: Object.freeze({
    status: () => invoke<FluentStatus>('meshing:status'),
    connect: (config: FluentConnectionConfig) => invoke<FluentStatus>('meshing:connect', config),
    disconnect: () => invoke<FluentStatus>('meshing:disconnect'),
    read: (request: MeshingReadRequest) => invoke<MeshingReadReport>('meshing:read', request),
    write: (request: MeshingWriteRequest) => invoke<MeshingWriteReport>('meshing:write', request),
    schemas: () => invoke<MeshingSchemaSummary[]>('meshing:schemas'),
    schema: (workflowType: MeshingWorkflowType) =>
      invoke<MeshingWorkflowSchema>('meshing:schema', workflowType),
    validatePreset: (preset: MeshingPresetDocument) =>
      invoke<MeshingPresetValidationReport>('meshing:validate-preset', preset),
  }),
  meshingAutomations: Object.freeze({
    list: () => invoke<MeshingAutomation[]>('meshing-automations:list'),
    create: (payload: MeshingAutomationInput) =>
      invoke<MeshingAutomation>('meshing-automations:create', payload),
    get: (id: number) => invoke<MeshingAutomation>('meshing-automations:get', id),
    update: (id: number, payload: MeshingAutomationInput) =>
      invoke<MeshingAutomation>('meshing-automations:update', id, payload),
    delete: (id: number) => invoke<void>('meshing-automations:delete', id),
    validate: (id: number) =>
      invoke<MeshingPresetValidationReport>('meshing-automations:validate', id),
    apply: (id: number, payload: ApplyMeshingAutomationRequest) =>
      invoke<MeshingWorkflowReport>('meshing-automations:apply', id, payload),
  }),
  fluent: Object.freeze({
    status: () => invoke<FluentStatus>('fluent:status'),
    connect: (config: FluentConnectionConfig) => invoke<FluentStatus>('fluent:connect', config),
    disconnect: () => invoke<FluentStatus>('fluent:disconnect'),
    catalog: () => invoke<SettingCatalogEntry[]>('fluent:catalog'),
    readSettings: (settingIds: string[]) =>
      invoke<Record<string, PresetValue>>('fluent:read-settings', settingIds),
    writeSettings: (items: PresetItem[]) =>
      invoke<FluentOperationReport>('fluent:write-settings', items),
    validatePreset: (preset: PresetDocument) =>
      invoke<PresetValidationReport>('fluent:validate-preset', preset),
    applyPreset: (preset: PresetDocument) =>
      invoke<FluentOperationReport>('fluent:apply-preset', preset),
  }),
  workflows: Object.freeze({
    applyAutomation: (automationId: number, payload: ApplyAutomationRequest) =>
      invoke<WorkflowReport>('workflows:apply-automation', automationId, payload),
  }),
})

contextBridge.exposeInMainWorld('fluentAI', api)
