import { app, BrowserWindow, shell } from 'electron'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'

import type { SidecarStatus } from '../shared/contracts'
import { registerBusinessIpc } from './business-ipc'
import { createElectronCredentialStore } from './electron-credentials'
import { ElectronModelFilePicker } from './electron-model-files'
import { registerSidecarIpc, SIDECAR_STATUS_CHANGED_CHANNEL } from './ipc'
import { ModelFileRegistry } from './model-file-registry'
import { resolveSidecarDataDirectory, SidecarManager } from './sidecar'

let mainWindow: BrowserWindow | null = null
let quitAfterSidecarStop = false
const smokeTest = process.env.FLUENT_AI_SMOKE_TEST === '1'
let smokeRendererLoaded = false
let smokeSidecarStatus: SidecarStatus | null = null

const completeSmokeTestIfReady = (): void => {
  if (!smokeTest || !smokeRendererLoaded || smokeSidecarStatus === null) return
  const reportPath = process.env.FLUENT_AI_SMOKE_REPORT
  if (reportPath) {
    writeFileSync(
      reportPath,
      JSON.stringify(
        {
          status: 'passed',
          app_version: app.getVersion(),
          is_packaged: app.isPackaged,
          resources_path: process.resourcesPath,
          sidecar: smokeSidecarStatus,
        },
        null,
        2,
      ),
      'utf8',
    )
  }
  app.quit()
}

const failSmokeTest = (error: unknown): void => {
  if (!smokeTest) return
  const reportPath = process.env.FLUENT_AI_SMOKE_REPORT
  if (reportPath) {
    writeFileSync(
      reportPath,
      JSON.stringify(
        {
          status: 'failed',
          error: error instanceof Error ? error.message : String(error),
        },
        null,
        2,
      ),
      'utf8',
    )
  }
  app.exit(1)
}

const sidecarRoot = app.isPackaged ? join(process.resourcesPath, 'sidecar') : app.getAppPath()
const sidecar = new SidecarManager({
  appRoot: sidecarRoot,
  pythonExecutable: app.isPackaged
    ? join(sidecarRoot, 'python', 'python.exe')
    : process.env.FLUENT_AI_PYTHON,
  dataDirectory: resolveSidecarDataDirectory(app.getPath('userData')),
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
    if (!smokeTest) window.show()
  })

  window.webContents.once('did-finish-load', () => {
    window.webContents.send(SIDECAR_STATUS_CHANGED_CHANNEL, sidecar.getStatus())
    smokeRendererLoaded = true
    completeSmokeTestIfReady()
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
  const modelFiles = new ModelFileRegistry()
  registerBusinessIpc({
    sidecar,
    modelFiles,
    modelFilePicker: new ElectronModelFilePicker(modelFiles),
    credentials: createElectronCredentialStore(app.getPath('userData')),
  })

  createMainWindow()

  void sidecar
    .start()
    .then((status) => {
      smokeSidecarStatus = status
      completeSmokeTestIfReady()
    })
    .catch((error: unknown) => {
      console.error('Failed to start sidecar:', error)
      failSmokeTest(error)
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
