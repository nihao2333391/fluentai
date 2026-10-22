import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'

import type { CredentialStatus } from '../shared/contracts'

export interface SecretProtector {
  isAvailable: () => Promise<boolean>
  encryptString: (value: string) => Promise<Buffer>
  decryptString: (value: Buffer) => Promise<string>
}

interface StoredCredential {
  version: 1
  ciphertext: string
}

export class CredentialStore {
  constructor(
    private readonly filePath: string,
    private readonly protector: SecretProtector,
  ) {}

  async getStatus(): Promise<CredentialStatus> {
    return {
      encryptionAvailable: await this.protector.isAvailable(),
      configured: existsSync(this.filePath),
    }
  }

  async setFluentPassword(password: string): Promise<CredentialStatus> {
    if (!password) {
      throw new Error('Fluent password must not be empty.')
    }
    if (!(await this.protector.isAvailable())) {
      throw new Error('Secure credential storage is unavailable on this system.')
    }

    const encrypted = await this.protector.encryptString(password)
    const payload: StoredCredential = {
      version: 1,
      ciphertext: encrypted.toString('base64'),
    }
    mkdirSync(dirname(this.filePath), { recursive: true })
    const temporaryPath = `${this.filePath}.tmp`
    writeFileSync(temporaryPath, JSON.stringify(payload), { encoding: 'utf8', mode: 0o600 })
    if (existsSync(this.filePath)) {
      rmSync(this.filePath, { force: true })
    }
    renameSync(temporaryPath, this.filePath)
    return this.getStatus()
  }

  async clearFluentPassword(): Promise<CredentialStatus> {
    if (existsSync(this.filePath)) {
      rmSync(this.filePath, { force: true })
    }
    return this.getStatus()
  }

  async readFluentPassword(): Promise<string> {
    if (!(await this.protector.isAvailable())) {
      throw new Error('Secure credential storage is unavailable on this system.')
    }
    if (!existsSync(this.filePath)) {
      throw new Error('No Fluent password is configured.')
    }
    const payload = JSON.parse(readFileSync(this.filePath, 'utf8')) as StoredCredential
    if (payload.version !== 1 || typeof payload.ciphertext !== 'string') {
      throw new Error('Stored Fluent credential format is invalid.')
    }
    return this.protector.decryptString(Buffer.from(payload.ciphertext, 'base64'))
  }
}
