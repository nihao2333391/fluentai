import { contextBridge } from 'electron'

const api = Object.freeze({
  platform: process.platform,
})

contextBridge.exposeInMainWorld('fluentAI', api)
