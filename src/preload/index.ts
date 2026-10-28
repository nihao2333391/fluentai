import { contextBridge, ipcRenderer } from 'electron'

import type {
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
  MeshingLiveSessionSnapshot,
  MeshingLiveSessionStart,
  MeshingLiveStepReport,
  MeshingLiveStepRequest,
  MeshingLiveWriteRequest,
  MeshingPresetDocument,
  MeshingPresetValidationReport,
  MeshingReadReport,
  MeshingReadRequest,
  MeshingSchemaSummary,
  MeshingWorkflowContract,
  MeshingWorkflowSchema,
  MeshingWorkflowType,
  MeshingWriteReport,
  MeshingWriteRequest,
  Model,
  ModelCreateRequest,
  ModelOpenReport,
  ModelUpdateRequest,
  OpenModelRequest,
  PickedModelFile,
  PresetDocument,
  PresetItem,
  PresetValidationReport,
  PresetValue,
  RestoreDatabaseReport,
  SettingCatalogEntry,
  SettingsPayload,
  SidecarStatus,
  SyncLog,
  SyncLogQuery,
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
  models: Object.freeze({
    list: () => invoke<Model[]>('models:list'),
    get: (id: number) => invoke<Model>('models:get', id),
    pickFile: () => invoke<PickedModelFile | null>('models:pick-file'),
    create: (payload: ModelCreateRequest) => invoke<Model>('models:create', payload),
    update: (id: number, payload: ModelUpdateRequest) =>
      invoke<Model>('models:update', id, payload),
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
    workflowSchema: (workflowType: MeshingWorkflowType) =>
      invoke<MeshingWorkflowContract>('meshing:workflow-schema', workflowType),
    schemas: () => invoke<MeshingSchemaSummary[]>('meshing:schemas'),
    schema: (workflowType: MeshingWorkflowType) =>
      invoke<MeshingWorkflowSchema>('meshing:schema', workflowType),
    validatePreset: (preset: MeshingPresetDocument) =>
      invoke<MeshingPresetValidationReport>('meshing:validate-preset', preset),
    inspectReferenceModel: (modelId: number) =>
      invoke<import('../shared/contracts').MeshingReferenceInspection>('meshing:inspect-reference', modelId),
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
  }),
  meshingLive: Object.freeze({
    start: (payload: MeshingLiveSessionStart) =>
      invoke<MeshingLiveSessionSnapshot>('meshing-live:start', payload),
    get: (sessionId: string) => invoke<MeshingLiveSessionSnapshot>('meshing-live:get', sessionId),
    enterStep: (sessionId: string, payload: MeshingLiveStepRequest) =>
      invoke<MeshingLiveStepReport>('meshing-live:enter-step', sessionId, payload),
    readStep: (sessionId: string, stepIndex: number) =>
      invoke<MeshingLiveStepReport>('meshing-live:read-step', sessionId, stepIndex),
    writeStep: (sessionId: string, payload: MeshingLiveWriteRequest) =>
      invoke<MeshingLiveStepReport>('meshing-live:write-step', sessionId, payload),
    executeStep: (sessionId: string, payload: MeshingLiveStepRequest) =>
      invoke<MeshingLiveStepReport>('meshing-live:execute-step', sessionId, payload),
    retryPrepare: (sessionId: string) =>
      invoke<MeshingLiveSessionSnapshot>('meshing-live:retry-prepare', sessionId),
    nextModel: (sessionId: string) =>
      invoke<MeshingLiveSessionSnapshot>('meshing-live:next-model', sessionId),
    retryModel: (sessionId: string) =>
      invoke<MeshingLiveSessionSnapshot>('meshing-live:retry-model', sessionId),
    stop: (sessionId: string) => invoke<MeshingLiveSessionSnapshot>('meshing-live:stop', sessionId),
    pickMeshFile: () => invoke<string | null>('meshing-live:pick-mesh'),
    archive: (sessionId: string, payload: import('../shared/contracts').MeshingArchiveCreate) =>
      invoke<import('../shared/contracts').MeshingArchiveRecord>('meshing-live:archive', sessionId, payload),
    archives: (sessionId: string) =>
      invoke<import('../shared/contracts').MeshingArchiveRecord[]>('meshing-live:archives', sessionId),
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
})

contextBridge.exposeInMainWorld('fluentAI', api)
