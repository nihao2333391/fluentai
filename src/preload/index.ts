import { contextBridge, ipcRenderer } from 'electron'

import type {
  Automation,
  AutomationInput,
  CredentialStatus,
  FluentAIApi,
  Job,
  Model,
  ModelAssociationRequest,
  ModelCreateRequest,
  ModelUpdateRequest,
  PickedModelFile,
  SettingsPayload,
  SidecarStatus,
  SyncLog,
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
  }),
  syncLogs: Object.freeze({
    list: (limit = 100) => invoke<SyncLog[]>('sync-logs:list', limit),
  }),
  credentials: Object.freeze({
    getStatus: () => invoke<CredentialStatus>('credentials:status'),
    setFluentPassword: (password: string) =>
      invoke<CredentialStatus>('credentials:set-fluent-password', password),
    clearFluentPassword: () => invoke<CredentialStatus>('credentials:clear-fluent-password'),
  }),
})

contextBridge.exposeInMainWorld('fluentAI', api)
