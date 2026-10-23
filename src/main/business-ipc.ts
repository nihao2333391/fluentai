import { BrowserWindow, ipcMain } from 'electron'

import type {
  Automation,
  AutomationInput,
  ApplyAutomationRequest,
  ApplyMeshingAutomationRequest,
  CredentialStatus,
  DatabaseBackupInfo,
  DatabaseBackupList,
  FluentConnectionConfig,
  FluentOperationReport,
  FluentStatus,
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
  PresetDocument,
  PresetItem,
  PresetValidationReport,
  PresetValue,
  RecentSession,
  RestoreDatabaseReport,
  SettingCatalogEntry,
  SettingsPayload,
  SyncLog,
  SyncLogQuery,
  WorkflowReport,
} from '../shared/contracts'
import type { CredentialStore } from './credential-store'
import type { ElectronModelFilePicker } from './electron-model-files'
import type { ModelFileRegistry } from './model-file-registry'
import type { SidecarManager } from './sidecar'

interface BusinessIpcOptions {
  sidecar: SidecarManager
  modelFiles: ModelFileRegistry
  modelFilePicker: ElectronModelFilePicker
  credentials: CredentialStore
}

const jsonBody = (value: unknown): string => JSON.stringify(value)

export function registerBusinessIpc(options: BusinessIpcOptions): void {
  const { sidecar, modelFiles, modelFilePicker, credentials } = options

  ipcMain.handle('automations:list', () => sidecar.request<Automation[]>('/api/automations'))
  ipcMain.handle('automations:create', (_event, payload: AutomationInput) =>
    sidecar.request<Automation>('/api/automations', {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('automations:get', (_event, id: number) =>
    sidecar.request<Automation>(`/api/automations/${id}`),
  )
  ipcMain.handle('automations:update', (_event, id: number, payload: AutomationInput) =>
    sidecar.request<Automation>(`/api/automations/${id}`, {
      method: 'PUT',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('automations:delete', (_event, id: number) =>
    sidecar.request<void>(`/api/automations/${id}`, { method: 'DELETE' }),
  )

  ipcMain.handle('models:list', () => sidecar.request<Model[]>('/api/models'))
  ipcMain.handle('models:get', (_event, id: number) => sidecar.request<Model>(`/api/models/${id}`))
  ipcMain.handle('models:pick-file', () =>
    modelFilePicker.pickFile(BrowserWindow.getFocusedWindow()),
  )
  ipcMain.handle('models:create', (_event, payload: ModelCreateRequest) => {
    const selected = modelFiles.resolve(payload.fileToken)
    return sidecar.request<Model>('/api/models', {
      method: 'POST',
      body: jsonBody({
        name: payload.name,
        file_path: selected.filePath,
        description: payload.description ?? '',
        tags: payload.tags ?? [],
      }),
    })
  })
  ipcMain.handle('models:update', async (_event, id: number, payload: ModelUpdateRequest) => {
    const current = await sidecar.request<Model>(`/api/models/${id}`)
    const filePath = payload.fileToken
      ? modelFiles.resolve(payload.fileToken).filePath
      : current.file_path
    return sidecar.request<Model>(`/api/models/${id}`, {
      method: 'PUT',
      body: jsonBody({
        name: payload.name,
        file_path: filePath,
        description: payload.description ?? current.description,
        tags: payload.tags ?? current.tags,
      }),
    })
  })
  ipcMain.handle('models:associate', (_event, id: number, payload: ModelAssociationRequest) =>
    sidecar.request<Model>(`/api/models/${id}/associate`, {
      method: 'POST',
      body: jsonBody({
        automation_id: payload.automationId,
        is_default: payload.isDefault,
      }),
    }),
  )
  ipcMain.handle('models:open', (_event, id: number, payload: OpenModelRequest) =>
    sidecar.request<ModelOpenReport>(`/api/models/${id}/open`, {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('models:refresh', (_event, id: number) =>
    sidecar.request<Model>(`/api/models/${id}/refresh`, { method: 'POST' }),
  )
  ipcMain.handle('models:delete', (_event, id: number) =>
    sidecar.request<void>(`/api/models/${id}`, { method: 'DELETE' }),
  )

  ipcMain.handle('settings:get', () => sidecar.request<SettingsPayload>('/api/settings'))
  ipcMain.handle('settings:update', (_event, payload: SettingsPayload) =>
    sidecar.request<SettingsPayload>('/api/settings', {
      method: 'PUT',
      body: jsonBody(payload),
    }),
  )

  ipcMain.handle('jobs:list', (_event, limit = 50) =>
    sidecar.request<Job[]>(`/api/jobs?limit=${Math.max(1, Math.min(limit, 200))}`),
  )
  ipcMain.handle('jobs:get', (_event, id: string) =>
    sidecar.request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  )
  ipcMain.handle('jobs:cancel', (_event, id: string) =>
    sidecar.request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  )

  ipcMain.handle('sync-logs:list', (_event, query: SyncLogQuery = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(Math.max(1, Math.min(query.limit ?? 100, 500))))
    if (query.direction) params.set('direction', query.direction)
    if (query.status) params.set('status_filter', query.status)
    if (query.automationId) params.set('automation_id', String(query.automationId))
    if (query.meshingAutomationId)
      params.set('meshing_automation_id', String(query.meshingAutomationId))
    if (query.modelId) params.set('model_id', String(query.modelId))
    if (query.search?.trim()) params.set('search', query.search.trim())
    return sidecar.request<SyncLog[]>(`/api/sync-logs?${params.toString()}`)
  })

  ipcMain.handle('session:recent', () => sidecar.request<RecentSession>('/api/session/recent'))

  ipcMain.handle('system:list-backups', () =>
    sidecar.request<DatabaseBackupList>('/api/system/backups'),
  )
  ipcMain.handle('system:create-backup', () =>
    sidecar.request<DatabaseBackupInfo>('/api/system/backups', { method: 'POST' }),
  )
  ipcMain.handle('system:restore-backup', (_event, backupName: string) =>
    sidecar.request<RestoreDatabaseReport>('/api/system/restore', {
      method: 'POST',
      body: jsonBody({ backup_name: backupName }),
    }),
  )

  ipcMain.handle('meshing:status', () => sidecar.request<FluentStatus>('/api/meshing/status'))
  ipcMain.handle('meshing:connect', (_event, payload: FluentConnectionConfig) =>
    sidecar.request<FluentStatus>('/api/meshing/connect', {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('meshing:disconnect', () =>
    sidecar.request<FluentStatus>('/api/meshing/disconnect', { method: 'POST' }),
  )
  ipcMain.handle('meshing:read', (_event, payload: MeshingReadRequest) =>
    sidecar.request<MeshingReadReport>('/api/meshing/read', {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('meshing:write', (_event, payload: MeshingWriteRequest) =>
    sidecar.request<MeshingWriteReport>('/api/meshing/write', {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('meshing:schemas', () =>
    sidecar.request<MeshingSchemaSummary[]>('/api/meshing/schemas'),
  )
  ipcMain.handle('meshing:schema', (_event, workflowType: MeshingWorkflowType) =>
    sidecar.request<MeshingWorkflowSchema>(`/api/meshing/schemas/${workflowType}`),
  )
  ipcMain.handle('meshing:validate-preset', (_event, preset: MeshingPresetDocument) =>
    sidecar.request<MeshingPresetValidationReport>('/api/meshing/presets/validate', {
      method: 'POST',
      body: jsonBody(preset),
    }),
  )
  ipcMain.handle('meshing-automations:list', () =>
    sidecar.request<MeshingAutomation[]>('/api/meshing-automations'),
  )
  ipcMain.handle('meshing-automations:create', (_event, payload: MeshingAutomationInput) =>
    sidecar.request<MeshingAutomation>('/api/meshing-automations', {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('meshing-automations:get', (_event, id: number) =>
    sidecar.request<MeshingAutomation>(`/api/meshing-automations/${id}`),
  )
  ipcMain.handle(
    'meshing-automations:update',
    (_event, id: number, payload: MeshingAutomationInput) =>
      sidecar.request<MeshingAutomation>(`/api/meshing-automations/${id}`, {
        method: 'PUT',
        body: jsonBody(payload),
      }),
  )
  ipcMain.handle('meshing-automations:delete', (_event, id: number) =>
    sidecar.request<void>(`/api/meshing-automations/${id}`, { method: 'DELETE' }),
  )
  ipcMain.handle('meshing-automations:validate', (_event, id: number) =>
    sidecar.request<MeshingPresetValidationReport>(`/api/meshing-automations/${id}/validate`, {
      method: 'POST',
    }),
  )
  ipcMain.handle(
    'meshing-automations:apply',
    (_event, id: number, payload: ApplyMeshingAutomationRequest) =>
      sidecar.request<MeshingWorkflowReport>(`/api/meshing-automations/${id}/apply`, {
        method: 'POST',
        body: jsonBody(payload),
      }),
  )

  ipcMain.handle('fluent:status', () => sidecar.request<FluentStatus>('/api/fluent/status'))
  ipcMain.handle('fluent:connect', (_event, payload: FluentConnectionConfig) =>
    sidecar.request<FluentStatus>('/api/fluent/connect', {
      method: 'POST',
      body: jsonBody(payload),
    }),
  )
  ipcMain.handle('fluent:disconnect', () =>
    sidecar.request<FluentStatus>('/api/fluent/disconnect', { method: 'POST' }),
  )
  ipcMain.handle('fluent:catalog', () =>
    sidecar.request<SettingCatalogEntry[]>('/api/fluent/catalog'),
  )
  ipcMain.handle('fluent:read-settings', (_event, settingIds: string[]) =>
    sidecar.request<Record<string, PresetValue>>('/api/fluent/settings/read', {
      method: 'POST',
      body: jsonBody({ setting_ids: settingIds }),
    }),
  )
  ipcMain.handle('fluent:write-settings', (_event, items: PresetItem[]) =>
    sidecar.request<FluentOperationReport>('/api/fluent/settings/write', {
      method: 'POST',
      body: jsonBody({ items }),
    }),
  )
  ipcMain.handle('fluent:validate-preset', (_event, preset: PresetDocument) =>
    sidecar.request<PresetValidationReport>('/api/fluent/presets/validate', {
      method: 'POST',
      body: jsonBody(preset),
    }),
  )
  ipcMain.handle('fluent:apply-preset', (_event, preset: PresetDocument) =>
    sidecar.request<FluentOperationReport>('/api/fluent/presets/apply', {
      method: 'POST',
      body: jsonBody(preset),
    }),
  )
  ipcMain.handle(
    'workflows:apply-automation',
    (_event, automationId: number, payload: ApplyAutomationRequest) =>
      sidecar.request<WorkflowReport>(`/api/automations/${automationId}/apply`, {
        method: 'POST',
        body: jsonBody(payload),
      }),
  )

  ipcMain.handle('credentials:status', (): Promise<CredentialStatus> => credentials.getStatus())
  ipcMain.handle('credentials:set-fluent-password', (_event, password: string) =>
    credentials.setFluentPassword(password),
  )
  ipcMain.handle('credentials:clear-fluent-password', () => credentials.clearFluentPassword())
}
