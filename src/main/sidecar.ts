import { randomBytes } from 'node:crypto'
import { spawn, type ChildProcessByStdio } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { existsSync } from 'node:fs'
import { delimiter, join, resolve } from 'node:path'
import type { Readable, Writable } from 'node:stream'

import type { SidecarHandshake, SidecarReadyResponse, SidecarStatus } from '../shared/contracts'

interface SidecarManagerOptions {
  appRoot: string
  pythonExecutable?: string
  dataDirectory?: string
  startTimeoutMs?: number
  stopTimeoutMs?: number
  maxAutoRestarts?: number
}

type SidecarChild = ChildProcessByStdio<Writable, Readable, Readable>

const DEFAULT_START_TIMEOUT_MS = 60_000
const DEFAULT_STOP_TIMEOUT_MS = 5_000
const DEFAULT_MAX_AUTO_RESTARTS = 2
const DEFAULT_REQUEST_TIMEOUT_MS = 15_000

const formatErrorDetail = (detail: unknown): string => {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item !== 'object' || item === null) return String(item)
        const entry = item as { loc?: unknown; msg?: unknown }
        const location = Array.isArray(entry.loc) ? entry.loc.map(String).join('.') : ''
        const message = typeof entry.msg === 'string' ? entry.msg : JSON.stringify(item)
        return location ? `${location}: ${message}` : message
      })
      .join('; ')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return String(detail ?? '')
}

export const resolveSidecarDataDirectory = (
  userDataDirectory: string,
  configuredDataDirectory = process.env.FLUENT_AI_DATA_DIR,
): string =>
  configuredDataDirectory?.trim()
    ? resolve(configuredDataDirectory)
    : join(userDataDirectory, 'data')

interface SidecarRequestInit extends RequestInit {
  timeoutMs?: number
}

export class SidecarManager extends EventEmitter {
  private readonly appRoot: string
  private readonly backendDirectory: string
  private readonly pythonExecutable?: string
  private readonly dataDirectory?: string
  private readonly startTimeoutMs: number
  private readonly stopTimeoutMs: number
  private readonly maxAutoRestarts: number

  private child: SidecarChild | null = null
  private token: string | null = null
  private port: number | null = null
  private stopping = false
  private startPromise: Promise<SidecarStatus> | null = null
  private restartTimer: NodeJS.Timeout | null = null
  private restartAttempts = 0
  private lastStderr = ''
  private status: SidecarStatus = {
    state: 'stopped',
    message: 'Sidecar has not started.',
  }

  constructor(options: SidecarManagerOptions) {
    super()
    this.appRoot = options.appRoot
    this.backendDirectory = join(options.appRoot, 'backend')
    this.pythonExecutable = options.pythonExecutable
    this.dataDirectory = options.dataDirectory
    this.startTimeoutMs = options.startTimeoutMs ?? DEFAULT_START_TIMEOUT_MS
    this.stopTimeoutMs = options.stopTimeoutMs ?? DEFAULT_STOP_TIMEOUT_MS
    this.maxAutoRestarts = options.maxAutoRestarts ?? DEFAULT_MAX_AUTO_RESTARTS
  }

  getStatus(): SidecarStatus {
    return { ...this.status }
  }

  onStatusChanged(listener: (status: SidecarStatus) => void): () => void {
    this.on('status', listener)
    return () => {
      this.off('status', listener)
    }
  }

  async start(): Promise<SidecarStatus> {
    if (this.status.state === 'ready' && this.child && this.child.exitCode === null) {
      return this.getStatus()
    }
    if (this.startPromise) {
      return this.startPromise
    }

    this.startPromise = this.doStart().finally(() => {
      this.startPromise = null
    })
    return this.startPromise
  }

  async request<T>(path: string, init: SidecarRequestInit = {}): Promise<T> {
    if (!path.startsWith('/api/')) {
      throw new Error('Sidecar requests must use an authenticated /api path.')
    }
    if (this.status.state !== 'ready' || !this.port || !this.token) {
      throw new Error('Sidecar is not ready.')
    }

    const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, ...requestInit } = init
    const headers = new Headers(requestInit.headers)
    headers.set('Authorization', `Bearer ${this.token}`)
    if (requestInit.body !== undefined && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }

    const response = await fetch(`http://127.0.0.1:${this.port}${path}`, {
      ...requestInit,
      headers,
      signal: requestInit.signal ?? AbortSignal.timeout(timeoutMs),
    })

    if (response.status === 204) {
      return undefined as T
    }

    const text = await response.text()
    let payload: unknown = null
    if (text) {
      try {
        payload = JSON.parse(text)
      } catch {
        payload = text
      }
    }

    if (!response.ok) {
      const rawDetail =
        typeof payload === 'object' && payload !== null && 'detail' in payload
          ? (payload as { detail: unknown }).detail
          : `HTTP ${response.status}`
      throw new Error(`Sidecar request failed: ${formatErrorDetail(rawDetail)}`)
    }

    return payload as T
  }

  async streamRequest<T>(
    path: string,
    init: SidecarRequestInit,
    onEvent: (event: T) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    if (!path.startsWith('/api/')) {
      throw new Error('Sidecar requests must use an authenticated /api path.')
    }
    if (this.status.state !== 'ready' || !this.port || !this.token) {
      throw new Error('Sidecar is not ready.')
    }
    const { timeoutMs = 300_000, ...requestInit } = init
    const headers = new Headers(requestInit.headers)
    headers.set('Authorization', `Bearer ${this.token}`)
    if (requestInit.body !== undefined && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    const response = await fetch(`http://127.0.0.1:${this.port}${path}`, {
      ...requestInit,
      headers,
      signal: signal ?? AbortSignal.timeout(timeoutMs),
    })
    if (!response.ok) {
      const body = await response.text()
      let detail = body
      try {
        const parsed = JSON.parse(body) as { detail?: unknown }
        if (parsed.detail !== undefined) detail = formatErrorDetail(parsed.detail)
      } catch {
        // Keep the original response text for non-JSON errors.
      }
      throw new Error(`Sidecar request failed: ${detail || `HTTP ${response.status}`}`)
    }
    if (!response.body) throw new Error('Sidecar did not return a stream.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    const emitFrames = (): void => {
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        const data = frame
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (!data) continue
        try {
          onEvent(JSON.parse(data) as T)
        } catch {
          // Ignore malformed frames and continue receiving later events.
        }
      }
    }
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        emitFrames()
      }
      buffer += decoder.decode()
      if (buffer.trim()) {
        const data = buffer
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (data) onEvent(JSON.parse(data) as T)
      }
    } finally {
      reader.releaseLock()
    }
  }

  async restart(): Promise<SidecarStatus> {
    this.restartAttempts = 0
    await this.stop()
    return this.start()
  }

  async stop(): Promise<SidecarStatus> {
    this.stopping = true
    this.clearRestartTimer()

    const child = this.child
    if (child) {
      try {
        await this.requestShutdown()
      } catch {
        // Fall back to process termination if graceful shutdown fails.
      }

      await this.waitForExit(child, this.stopTimeoutMs)
      if (child.exitCode === null && child.signalCode === null) {
        child.kill()
        await this.waitForExit(child, 2_000)
      }
    }

    this.child = null
    this.token = null
    this.port = null
    this.setStatus({ state: 'stopped', message: 'Sidecar stopped.' })
    return this.getStatus()
  }

  private async doStart(): Promise<SidecarStatus> {
    this.clearRestartTimer()
    this.stopping = false
    this.lastStderr = ''

    try {
      const pythonExecutable = this.resolvePythonExecutable()
      if (!existsSync(this.backendDirectory)) {
        throw new Error(`Sidecar backend directory does not exist: ${this.backendDirectory}`)
      }

      const token = randomBytes(32).toString('hex')
      this.token = token
      this.port = null
      this.setStatus({ state: 'starting', message: 'Starting FastAPI sidecar...' })

      const bundledPythonHome = join(this.appRoot, 'python')
      const bundledSitePackages = join(this.appRoot, 'site-packages')
      const pythonPathEntries = [
        this.backendDirectory,
        ...(existsSync(bundledSitePackages) ? [bundledSitePackages] : []),
        ...(process.env.PYTHONPATH ? [process.env.PYTHONPATH] : []),
      ]
      const sidecarEnvironment: NodeJS.ProcessEnv = {
        ...process.env,
        FLUENT_AI_SIDECAR_TOKEN: token,
        FLUENT_AI_PARENT_PIPE: '1',
        FLUENT_AI_DATA_DIR: this.dataDirectory,
        PYTHONPATH: pythonPathEntries.join(delimiter),
        PYTHONUNBUFFERED: '1',
        PYTHONNOUSERSITE: '1',
      }
      if (existsSync(join(bundledPythonHome, 'python.exe'))) {
        sidecarEnvironment.PYTHONHOME = bundledPythonHome
      }

      const child = spawn(pythonExecutable, ['-m', 'app.sidecar'], {
        cwd: this.backendDirectory,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: sidecarEnvironment,
      }) as SidecarChild

      this.child = child
      child.stderr.setEncoding('utf8')
      child.stderr.on('data', (chunk: string) => {
        this.lastStderr = `${this.lastStderr}${chunk}`.slice(-4_000)
        console.error(`[sidecar] ${chunk.trimEnd()}`)
      })
      child.once('exit', (code, signal) => {
        void this.handleExit(child, code, signal)
      })

      const handshake = await this.waitForHandshake(child)
      const ready = await this.requestReady(handshake.port, token)

      this.port = handshake.port
      this.restartAttempts = 0
      this.setStatus({
        state: 'ready',
        message: 'FastAPI sidecar is ready.',
        version: ready.version,
        pid: handshake.pid,
        port: handshake.port,
      })
      return this.getStatus()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      this.setStatus({
        state: 'error',
        message: this.lastStderr ? `${message}\n${this.lastStderr}` : message,
      })
      throw error
    }
  }

  private resolvePythonExecutable(): string {
    const candidates = [
      this.pythonExecutable,
      process.env.FLUENT_AI_PYTHON,
      join(this.appRoot, 'python', 'python.exe'),
      join(this.appRoot, '.venv', 'Scripts', 'python.exe'),
      join(this.appRoot, '.venv', 'bin', 'python'),
      'python',
    ].filter((value): value is string => Boolean(value))

    for (const candidate of candidates) {
      if (candidate === 'python' || candidate === 'py' || existsSync(candidate)) {
        return candidate
      }
    }

    throw new Error(
      `Python executable was not found. Expected ${join(this.appRoot, '.venv', 'Scripts', 'python.exe')}`,
    )
  }

  private waitForHandshake(
    child: SidecarChild,
  ): Promise<Extract<SidecarHandshake, { event: 'sidecar_ready' }>> {
    return new Promise((resolve, reject) => {
      let buffer = ''
      const timer = setTimeout(() => {
        finish(new Error(`Sidecar readiness timed out after ${this.startTimeoutMs} ms.`))
      }, this.startTimeoutMs)

      const finish = (
        error: Error | null,
        handshake?: Extract<SidecarHandshake, { event: 'sidecar_ready' }>,
      ): void => {
        clearTimeout(timer)
        child.stdout.off('data', onData)
        child.off('error', onError)
        child.off('exit', onExit)
        if (error) {
          reject(error)
        } else if (handshake) {
          resolve(handshake)
        }
      }

      const onData = (chunk: string): void => {
        buffer += chunk
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('{')) {
            continue
          }
          try {
            const message = JSON.parse(trimmed) as SidecarHandshake
            if (message.event === 'sidecar_error') {
              finish(new Error(message.message))
              return
            }
            if (
              message.event === 'sidecar_ready' &&
              Number.isInteger(message.port) &&
              message.port > 0 &&
              Number.isInteger(message.pid)
            ) {
              finish(null, message)
              return
            }
          } catch {
            // Non-JSON stdout is treated as diagnostic output.
          }
        }
      }

      const onError = (error: Error): void => {
        finish(error)
      }

      const onExit = (code: number | null, signal: NodeJS.Signals | null): void => {
        finish(new Error(`Sidecar exited before readiness (code=${code}, signal=${signal}).`))
      }

      child.stdout.setEncoding('utf8')
      child.stdout.on('data', onData)
      child.once('error', onError)
      child.once('exit', onExit)
    })
  }

  private async requestReady(port: number, token: string): Promise<SidecarReadyResponse> {
    const response = await fetch(`http://127.0.0.1:${port}/api/system/ready`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5_000),
    })
    if (!response.ok) {
      throw new Error(`Sidecar readiness request failed with HTTP ${response.status}.`)
    }
    const payload = (await response.json()) as SidecarReadyResponse
    if (
      payload.status !== 'ready' ||
      payload.service !== 'fluent-ai-sidecar' ||
      payload.database !== 'ready'
    ) {
      throw new Error('Sidecar returned an invalid readiness response.')
    }
    return payload
  }

  private async requestShutdown(): Promise<void> {
    if (!this.port || !this.token) {
      return
    }
    const response = await fetch(`http://127.0.0.1:${this.port}/api/system/shutdown`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.token}` },
      signal: AbortSignal.timeout(2_000),
    })
    if (!response.ok) {
      throw new Error(`Sidecar shutdown request failed with HTTP ${response.status}.`)
    }
  }

  private waitForExit(child: SidecarChild, timeoutMs: number): Promise<void> {
    if (child.exitCode !== null || child.signalCode !== null) {
      return Promise.resolve()
    }
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        child.off('exit', onExit)
        resolve()
      }, timeoutMs)
      const onExit = (): void => {
        clearTimeout(timer)
        resolve()
      }
      child.once('exit', onExit)
    })
  }

  private async handleExit(
    child: SidecarChild,
    code: number | null,
    signal: NodeJS.Signals | null,
  ): Promise<void> {
    if (this.child !== child) {
      return
    }

    this.child = null
    this.port = null
    this.token = null

    if (this.stopping) {
      this.setStatus({ state: 'stopped', message: 'Sidecar stopped.' })
      return
    }

    const message = `Sidecar exited unexpectedly (code=${code}, signal=${signal}).`
    this.setStatus({
      state: 'error',
      message: this.lastStderr ? `${message}\n${this.lastStderr}` : message,
    })
    this.scheduleRestart()
  }

  private scheduleRestart(): void {
    if (this.restartAttempts >= this.maxAutoRestarts || this.restartTimer) {
      return
    }

    this.restartAttempts += 1
    const delayMs = 500 * 2 ** (this.restartAttempts - 1)
    this.setStatus({
      state: 'restarting',
      message: `Restarting sidecar (attempt ${this.restartAttempts}/${this.maxAutoRestarts})...`,
    })
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null
      void this.start().catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error)
        this.setStatus({ state: 'error', message })
      })
    }, delayMs)
  }

  private clearRestartTimer(): void {
    if (this.restartTimer) {
      clearTimeout(this.restartTimer)
      this.restartTimer = null
    }
  }

  private setStatus(status: SidecarStatus): void {
    this.status = status
    this.emit('status', this.getStatus())
  }
}
