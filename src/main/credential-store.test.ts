// @vitest-environment node

import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { CredentialStore, type SecretProtector } from './credential-store'

const temporaryDirectories: string[] = []

const makeStore = (available = true): CredentialStore => {
  const directory = mkdtempSync(join(tmpdir(), 'fluent-ai-credentials-'))
  temporaryDirectories.push(directory)
  const protector: SecretProtector = {
    isAvailable: async () => available,
    encryptString: async (value) => Buffer.from([...Buffer.from(value, 'utf8')].reverse()),
    decryptString: async (value) => Buffer.from([...value].reverse()).toString('utf8'),
  }
  return new CredentialStore(join(directory, 'secrets', 'credentials.json'), protector)
}

afterEach(() => {
  while (temporaryDirectories.length > 0) {
    const directory = temporaryDirectories.pop()
    if (directory) {
      rmSync(directory, { recursive: true, force: true })
    }
  }
})

describe('CredentialStore', () => {
  it('encrypts, reads, reports, and clears a Fluent password', async () => {
    const store = makeStore()
    const password = 'super-secret-password'

    await expect(store.getStatus()).resolves.toEqual({
      encryptionAvailable: true,
      configured: false,
    })
    expect((await store.setFluentPassword(password)).configured).toBe(true)
    await expect(store.readFluentPassword()).resolves.toBe(password)

    const filePath = (store as unknown as { filePath: string }).filePath
    expect(readFileSync(filePath, 'utf8')).not.toContain(password)

    expect((await store.clearFluentPassword()).configured).toBe(false)
  })

  it('refuses to store credentials when secure storage is unavailable', async () => {
    const store = makeStore(false)
    await expect(store.setFluentPassword('secret')).rejects.toThrow(/unavailable/)
  })
})
