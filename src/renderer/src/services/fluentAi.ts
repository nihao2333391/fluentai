import type {
  ApplyAutomationRequest,
  ApplyMeshingAutomationRequest,
  AutomationInput,
  FluentAIApi,
  FluentConnectionConfig,
  MeshingAutomationInput,
  MeshingPresetDocument,
  MeshingWorkflowType,
  ModelAssociationRequest,
  ModelCreateRequest,
  OpenModelRequest,
  ModelUpdateRequest,
  PresetDocument,
  PresetItem,
  SettingsPayload,
} from '../../../shared/contracts'

export function getFluentAIApi(): FluentAIApi {
  const api = window.fluentAI
  if (!api) {
    throw new Error('Fluent AI preload API is unavailable.')
  }
  return api
}

export const fluentAiService = {
  automations: {
    list: () => getFluentAIApi().automations.list(),
    create: (payload: AutomationInput) => getFluentAIApi().automations.create(payload),
    get: (id: number) => getFluentAIApi().automations.get(id),
    update: (id: number, payload: AutomationInput) =>
      getFluentAIApi().automations.update(id, payload),
    delete: (id: number) => getFluentAIApi().automations.delete(id),
  },
  models: {
    list: () => getFluentAIApi().models.list(),
    get: (id: number) => getFluentAIApi().models.get(id),
    pickFile: () => getFluentAIApi().models.pickFile(),
    create: (payload: ModelCreateRequest) => getFluentAIApi().models.create(payload),
    update: (id: number, payload: ModelUpdateRequest) =>
      getFluentAIApi().models.update(id, payload),
    associate: (id: number, payload: ModelAssociationRequest) =>
      getFluentAIApi().models.associate(id, payload),
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
  },
  syncLogs: {
    list: (limit?: number) => getFluentAIApi().syncLogs.list(limit),
  },
  credentials: {
    getStatus: () => getFluentAIApi().credentials.getStatus(),
    setFluentPassword: (password: string) =>
      getFluentAIApi().credentials.setFluentPassword(password),
    clearFluentPassword: () => getFluentAIApi().credentials.clearFluentPassword(),
  },
  meshing: {
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
    apply: (id: number, payload: ApplyMeshingAutomationRequest) =>
      getFluentAIApi().meshingAutomations.apply(id, payload),
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
  workflows: {
    applyAutomation: (automationId: number, payload: ApplyAutomationRequest) =>
      getFluentAIApi().workflows.applyAutomation(automationId, payload),
  },
}
