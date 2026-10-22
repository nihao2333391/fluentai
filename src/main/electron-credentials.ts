import { safeStorage } from 'electron'
import { join } from 'node:path'

import { CredentialStore } from './credential-store'

export function createElectronCredentialStore(userDataDirectory: string): CredentialStore {
  return new CredentialStore(join(userDataDirectory, 'secrets', 'fluent-credentials.json'), {
    isAvailable: () => safeStorage.isAsyncEncryptionAvailable(),
    encryptString: (value) => safeStorage.encryptStringAsync(value),
    decryptString: async (value) => (await safeStorage.decryptStringAsync(value)).result,
  })
}
