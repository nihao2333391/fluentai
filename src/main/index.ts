import { app, BrowserWindow, shell } from 'electron'
import { join } from 'node:path'

import type { SidecarStatus } from '../shared/contracts'
import { registerSidecarIpc, SIDECAR_STATUS_CHANGED_CHANNEL } from './ipc'
import { SidecarManager } from './sidecar'

let mainWindow: BrowserWindow | null = null
let quitAfterSidecarStop = false

const sidecar = new SidecarManager({
  appRoot: app.getAppPath(),
  pythonExecutable: process.env.FLUENT_AI_PYTHON,
  dataDirectory: join(app.getPath('userData'), 'data'),
})

const broadcastSidecarStatus = (status: SidecarStatus): void => {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) {
      window.webContents.send(SIDECAR_STATUS_CHANGED_CHANNEL, status)
    }
  }
}

sidecar.onStatusChanged(broadcastSidecarStatus)
registerSidecarIpc(sidecar)

const createMainWindow = (): BrowserWindow => {
  const window = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 920,
    minHeight: 600,
    show: false,
    backgroundColor: '#0b1220',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  mainWindow = window

  window.once('ready-to-show', () => {
    window.show()
  })

  window.webContents.once('did-finish-load', () => {
    window.webContents.send(SIDECAR_STATUS_CHANGED_CHANNEL, sidecar.getStatus())
  })

  window.on('closed', () => {
    if (mainWindow === window) {
      mainWindow = null
    }
  })

  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })

  const rendererUrl = process.env.ELECTRON_RENDERER_URL
  if (rendererUrl) {
    void window.loadURL(rendererUrl)
  } else {
    void window.loadFile(join(__dirname, '../renderer/index.html'))
  }

  return window
}

app.whenReady().then(() => {
  createMainWindow()

  void sidecar.start().catch((error: unknown) => {
    console.error('Failed to start sidecar:', error)
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow()
    }
  })
})

app.on('before-quit', (event) => {
  if (quitAfterSidecarStop || sidecar.getStatus().state === 'stopped') {
    return
  }

  event.preventDefault()
  quitAfterSidecarStop = true
  void sidecar.stop().finally(() => {
    app.quit()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
