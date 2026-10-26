import type {
  FluentAIApi,
  FluentConnectionConfig,
  MeshingAutomationInput,
  MeshingLiveSessionStart,
  MeshingLiveStepRequest,
  MeshingLiveWriteRequest,
  MeshingPresetDocument,
  MeshingReadRequest,
  MeshingWriteRequest,
  MeshingWorkflowType,
  ModelCreateRequest,
  OpenModelRequest,
  ModelUpdateRequest,
  PresetDocument,
  PresetItem,
  SettingsPayload,
  SyncLogQuery,
} from '../../../shared/contracts'

export function getFluentAIApi(): FluentAIApi {
  const api = window.fluentAI
  if (!api) {
    throw new Error('Fluent AI preload API is unavailable.')
  }
  return api
}

export const fluentAiService = {
  models: {
    list: () => getFluentAIApi().models.list(),
    get: (id: number) => getFluentAIApi().models.get(id),
    pickFile: () => getFluentAIApi().models.pickFile(),
    create: (payload: ModelCreateRequest) => getFluentAIApi().models.create(payload),
    update: (id: number, payload: ModelUpdateRequest) =>
      getFluentAIApi().models.update(id, payload),
    open: (id: number, payload: OpenModelRequest) => getFluentAIApi().models.open(id, payload),
    refresh: (id: number) => getFluentAIApi().models.refresh(id),
    delete: (id: number) => getFluentAIApi().models.delete(id),
  },
  settings: {
    get: () => getFluentAIApi().settings.get(),
    update: (payload: SettingsPayload) => getFluentAIApi().settings.update(payload),
  },
  jobs: {
    list: (limit?: number) => getFluentAIApi().jobs.list(limit),
    get: (id: string) => getFluentAIApi().jobs.get(id),
    cancel: (id: string) => getFluentAIApi().jobs.cancel(id),
  },
  syncLogs: {
    list: (query?: SyncLogQuery) => getFluentAIApi().syncLogs.list(query),
  },
  system: {
    listBackups: () => getFluentAIApi().system.listBackups(),
    createBackup: () => getFluentAIApi().system.createBackup(),
    restoreBackup: (backupName: string) => getFluentAIApi().system.restoreBackup(backupName),
  },
  credentials: {
    getStatus: () => getFluentAIApi().credentials.getStatus(),
    setFluentPassword: (password: string) =>
      getFluentAIApi().credentials.setFluentPassword(password),
    clearFluentPassword: () => getFluentAIApi().credentials.clearFluentPassword(),
  },
  meshing: {
    status: () => getFluentAIApi().meshing.status(),
    connect: (config: FluentConnectionConfig) => getFluentAIApi().meshing.connect(config),
    disconnect: () => getFluentAIApi().meshing.disconnect(),
    read: (request: MeshingReadRequest) => getFluentAIApi().meshing.read(request),
    write: (request: MeshingWriteRequest) => getFluentAIApi().meshing.write(request),
    workflowSchema: (workflowType: MeshingWorkflowType) =>
      getFluentAIApi().meshing.workflowSchema(workflowType),
    schemas: () => getFluentAIApi().meshing.schemas(),
    schema: (workflowType: MeshingWorkflowType) => getFluentAIApi().meshing.schema(workflowType),
    validatePreset: (preset: MeshingPresetDocument) =>
      getFluentAIApi().meshing.validatePreset(preset),
  },
  meshingAutomations: {
    list: () => getFluentAIApi().meshingAutomations.list(),
    create: (payload: MeshingAutomationInput) =>
      getFluentAIApi().meshingAutomations.create(payload),
    get: (id: number) => getFluentAIApi().meshingAutomations.get(id),
    update: (id: number, payload: MeshingAutomationInput) =>
      getFluentAIApi().meshingAutomations.update(id, payload),
    delete: (id: number) => getFluentAIApi().meshingAutomations.delete(id),
    validate: (id: number) => getFluentAIApi().meshingAutomations.validate(id),
  },
  meshingLive: {
    start: (payload: MeshingLiveSessionStart) => getFluentAIApi().meshingLive.start(payload),
    get: (sessionId: string) => getFluentAIApi().meshingLive.get(sessionId),
    enterStep: (sessionId: string, payload: MeshingLiveStepRequest) =>
      getFluentAIApi().meshingLive.enterStep(sessionId, payload),
    readStep: (sessionId: string, stepIndex: number) =>
      getFluentAIApi().meshingLive.readStep(sessionId, stepIndex),
    writeStep: (sessionId: string, payload: MeshingLiveWriteRequest) =>
      getFluentAIApi().meshingLive.writeStep(sessionId, payload),
    executeStep: (sessionId: string, payload: MeshingLiveStepRequest) =>
      getFluentAIApi().meshingLive.executeStep(sessionId, payload),
    nextModel: (sessionId: string) => getFluentAIApi().meshingLive.nextModel(sessionId),
    retryModel: (sessionId: string) => getFluentAIApi().meshingLive.retryModel(sessionId),
    stop: (sessionId: string) => getFluentAIApi().meshingLive.stop(sessionId),
  },
  fluent: {
    status: () => getFluentAIApi().fluent.status(),
    connect: (config: FluentConnectionConfig) => getFluentAIApi().fluent.connect(config),
    disconnect: () => getFluentAIApi().fluent.disconnect(),
    catalog: () => getFluentAIApi().fluent.catalog(),
    readSettings: (settingIds: string[]) => getFluentAIApi().fluent.readSettings(settingIds),
    writeSettings: (items: PresetItem[]) => getFluentAIApi().fluent.writeSettings(items),
    validatePreset: (preset: PresetDocument) => getFluentAIApi().fluent.validatePreset(preset),
    applyPreset: (preset: PresetDocument) => getFluentAIApi().fluent.applyPreset(preset),
  },
}
