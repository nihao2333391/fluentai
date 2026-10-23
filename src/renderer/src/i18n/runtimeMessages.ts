import type { TFunction } from 'i18next'

const MESSAGE_KEYS: Record<string, string> = {
  'Loading resources.': 'loadingResources',
  'Fluent connected.': 'fluentConnected',
  'Model loaded.': 'modelLoaded',
  'Applying preset and verifying readback.': 'applyingAndVerifying',
  'Preset apply failed.': 'presetApplyFailed',
  'Automation applied with failures.': 'automationAppliedFailures',
  'Automation applied successfully.': 'automationAppliedSuccessfully',
  'Automation applied and verified.': 'automationAppliedVerified',
  'Automation workflow failed.': 'automationWorkflowFailed',
  'Preset validation failed.': 'presetValidationFailed',
  'Cancelled by user.': 'cancelledByUser',
  'Direct preset application.': 'directPresetApplication',
  'Automation apply failed readback verification.': 'automationApplyFailedReadback',
  'Model loaded into Fluent.': 'modelLoadedIntoFluent',
  'One or more settings failed readback verification.': 'oneOrMoreSettingsFailedReadback',
  'Fluent Meshing connected.': 'meshingConnected',
  'Importing geometry and validating names.': 'importingGeometry',
  'Meshing preset apply failed.': 'meshingApplyFailed',
  'Meshing apply failed.': 'meshingApplyFailed',
  'Meshing preset applied with failures.': 'meshingAppliedFailures',
  'Meshing preset applied successfully.': 'meshingAppliedSuccessfully',
  'Meshing preset applied and verified before mesh generation.': 'meshingAppliedVerified',
  'Meshing workflow failed.': 'meshingWorkflowFailed',
  'Sidecar has not started.': 'sidecarNotStarted',
  'Sidecar stopped.': 'sidecarStopped',
  'Starting FastAPI sidecar...': 'sidecarStarting',
  'FastAPI sidecar is ready.': 'sidecarReady',
  'Database restored. A pre-restore safety backup was created.': 'databaseRestored',
}

export const localizedRuntimeMessage = (t: TFunction, message: string): string => {
  const key = MESSAGE_KEYS[message]
  if (key) return t(`runtimeMessages.${key}`)

  const writeCount = /^(\d+) setting write\(s\)\.$/.exec(message)
  if (writeCount) {
    return t('runtimeMessages.settingWrites', { count: Number(writeCount[1]) })
  }

  return message
}
