import { contextBridge, ipcRenderer } from 'electron'

import type { FluentAIApi, SidecarStatus } from '../shared/contracts'

const api: FluentAIApi = Object.freeze({
  platform: process.platform,
  sidecar: Object.freeze({
    getStatus: () => ipcRenderer.invoke('sidecar:get-status') as Promise<SidecarStatus>,
    restart: () => ipcRenderer.invoke('sidecar:restart') as Promise<SidecarStatus>,
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
})

contextBridge.exposeInMainWorld('fluentAI', api)
