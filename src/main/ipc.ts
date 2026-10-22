import { ipcMain } from 'electron'

import type { SidecarManager } from './sidecar'

export const SIDECAR_GET_STATUS_CHANNEL = 'sidecar:get-status'
export const SIDECAR_RESTART_CHANNEL = 'sidecar:restart'
export const SIDECAR_STATUS_CHANGED_CHANNEL = 'sidecar:status-changed'

export function registerSidecarIpc(sidecar: SidecarManager): void {
  ipcMain.handle(SIDECAR_GET_STATUS_CHANNEL, () => sidecar.getStatus())
  ipcMain.handle(SIDECAR_RESTART_CHANNEL, () => sidecar.restart())
}
